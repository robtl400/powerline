import random
import string
import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, AdminUser, CurrentUser
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.auth import hash_password
from app.services.sms import send_sms

log = structlog.get_logger()
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> User:
    return current_user


@router.get("", response_model=list[UserResponse])
async def list_users(db: DB, _: AdminUser) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: DB,
    _: AdminUser,
) -> User:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    temp_password = body.password or "".join(random.choices(string.ascii_letters + string.digits, k=16))
    user = User(
        email=body.email,
        name=body.name,
        phone=body.phone,
        hashed_password=hash_password(temp_password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    try:
        send_sms(user.phone, f"You've been invited to Powerline. Your temporary password is: {temp_password}")
    except Exception:
        log.exception("invite_sms_failed", email=user.email)

    return user


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

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user
