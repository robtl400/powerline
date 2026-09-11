import secrets
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, AdminUser, CurrentUser
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.common import Page
from app.schemas.user import (
    UserCreate,
    UserCreateResponse,
    UserResponse,
    UserUpdate,
)
from app.services.auth import hash_password_async, revoke_user_sessions
from app.services.sms import send_sms_async

log = structlog.get_logger()
router = APIRouter(prefix="/users", tags=["users"])

# One key for the whole admin population: the guard asks how many admins exist,
# which every other demotion can change, so they queue behind one another.
_ADMIN_GUARD_LOCK_KEY = "powerline:last_admin_guard"


async def _lock_admin_guard(db: AsyncSession) -> None:
    """Serialise the last-admin check with the write it protects.

    Transaction-scoped: Postgres releases it at the commit that demotes or
    deactivates the user, so two concurrent demotions cannot both read a count
    taken before the other's write.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(CAST(:guard_key AS text)))"),
        {"guard_key": _ADMIN_GUARD_LOCK_KEY},
    )


async def _other_active_admins(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Count active admins other than user_id."""
    result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == "admin", User.is_active.is_(True), User.id != user_id)
    )
    return int(result.scalar_one())


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> User:
    return current_user


@router.get("", response_model=Page[UserResponse])
async def list_users(
    db: DB,
    _: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
) -> Page[UserResponse]:
    total = await db.scalar(select(func.count()).select_from(User))
    result = await db.execute(
        select(User).order_by(User.created_at).offset(skip).limit(limit)
    )
    return Page[UserResponse](
        total=int(total or 0),
        items=[UserResponse.model_validate(user) for user in result.scalars().all()],
    )


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: DB,
    _: AdminUser,
) -> UserCreateResponse:
    duplicate = HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
    )

    existing = await db.execute(select(User).where(func.lower(User.email) == body.email).limit(1))
    if existing.scalars().first():
        raise duplicate

    temp_password = None if body.password else secrets.token_urlsafe(12)
    user = User(
        email=body.email,
        name=body.name,
        phone=body.phone,
        hashed_password=await hash_password_async(body.password or temp_password),
        role=body.role,
    )
    db.add(user)
    # Two invites for one address can both clear the check above; the unique
    # index is what actually settles it.
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise duplicate
    await db.refresh(user)

    if temp_password:
        message = f"You've been invited to Powerline. Your temporary password is: {temp_password}"
    else:
        message = (
            "You've been invited to Powerline. "
            "Sign in with the password your administrator gave you."
        )

    invite_sent = True
    try:
        await send_sms_async(user.phone, message)
    except Exception:
        invite_sent = False
        log.warning("invite_sms_failed", user_id=str(user.id), exc_info=True)

    return UserCreateResponse(
        **UserResponse.model_validate(user).model_dump(),
        invite_sent=invite_sent,
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: DB,
    _: AdminUser,
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    changes = body.model_dump(exclude_unset=True)

    if user.role == "admin" and user.is_active:
        losing_admin = changes.get("is_active") is False or (
            "role" in changes and changes["role"] is not None and changes["role"] != "admin"
        )
        if losing_admin:
            await _lock_admin_guard(db)
            if await _other_active_admins(db, user.id) == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot deactivate or demote the last active admin",
                )

    # A user who loses access or changes role must not keep working with the
    # tokens they already hold.
    ends_sessions = changes.get("is_active") is False or (
        "role" in changes and changes["role"] is not None and changes["role"] != user.role
    )

    for field, value in changes.items():
        setattr(user, field, value)

    if ends_sessions:
        await revoke_user_sessions(get_redis(), str(user.id), db)

    await db.commit()
    await db.refresh(user)

    if ends_sessions:
        log.info("user_sessions_revoked", user_id=str(user.id))

    return user
