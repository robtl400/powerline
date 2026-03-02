import random
import string

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    ResetConfirm,
    ResetRequest,
    TokenResponse,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services.sms import send_sms

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])

RESET_CODE_TTL = 600  # 10 minutes


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> AccessTokenResponse:
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("wrong token type")
        user_id = payload["sub"]
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    return AccessTokenResponse(access_token=create_access_token(user_id))


@router.post("/reset-request", status_code=status.HTTP_204_NO_CONTENT)
async def reset_request(body: ResetRequest, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Always return 204 — don't reveal whether email exists
    if not user or not user.is_active:
        return

    code = "".join(random.choices(string.digits, k=6))
    await get_redis().setex(f"reset:{body.email}", RESET_CODE_TTL, code)

    try:
        send_sms(user.phone, f"Your Powerline reset code is: {code}")
    except Exception:
        log.exception("sms_send_failed", email=body.email)
        # Still return 204 — log the failure but don't expose it


@router.post("/reset-confirm", status_code=status.HTTP_204_NO_CONTENT)
async def reset_confirm(body: ResetConfirm, db: AsyncSession = Depends(get_db)) -> None:
    redis = get_redis()
    stored_code = await redis.get(f"reset:{body.email}")
    if not stored_code or stored_code != body.code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request")

    user.hashed_password = hash_password(body.new_password)
    await db.commit()

    await redis.delete(f"reset:{body.email}")
