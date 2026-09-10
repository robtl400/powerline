import asyncio
import hashlib
import hmac
import json
import secrets
import uuid

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.dependencies import get_client_ip
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
    consume_refresh_jti,
    create_access_token,
    decode_token,
    hash_password,
    issue_refresh_token,
    refresh_key,
    revoke_user_sessions,
    verify_password,
)
from app.services.rate_limiter import check_rate_limit
from app.services.sms import send_sms

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])

RESET_CODE_TTL = 600  # 10 minutes
RESET_MAX_ATTEMPTS = 5

# Compared against when the email is unknown so that a failed login costs the
# same time whether or not the account exists.
_DUMMY_HASH = hash_password("dummy-password")


def _email_fingerprint(email: str) -> str:
    """Truncated hash of an email, safe to put in logs."""
    return hashlib.sha256(email.encode()).hexdigest()[:12]


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    """Look up an account by email, ignoring case."""
    result = await db.execute(select(User).where(func.lower(User.email) == email).limit(1))
    return result.scalars().first()


async def _send_sms_async(to: str, body: str) -> str:
    """Run the blocking Twilio client off the event loop."""
    return await asyncio.get_running_loop().run_in_executor(None, send_sms, to, body)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    email = body.email.lower()
    redis = get_redis()
    await check_rate_limit(redis, "login-ip", get_client_ip(request), settings.AUTH_RATE_LIMIT * 3)
    await check_rate_limit(redis, "login-email", email, settings.AUTH_RATE_LIMIT)

    user = await _user_by_email(db, email)

    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(body.password, user.hashed_password) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=await issue_refresh_token(redis, user_id),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> AccessTokenResponse:
    """Exchange a refresh token for a new pair, retiring the token that was used.

    Each refresh token is registered in Redis and consumed on use, so replaying
    one — from a stolen copy, or after logout — is rejected.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
    )

    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("wrong token type")
        user_id = uuid.UUID(payload["sub"])
        jti = str(payload["jti"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise invalid

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise invalid

    redis = get_redis()
    if not await consume_refresh_jti(redis, str(user.id), jti):
        log.warning("refresh_token_replayed", user_id=str(user.id))
        raise invalid

    return AccessTokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=await issue_refresh_token(redis, str(user.id)),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest) -> None:
    """Retire one refresh token. Always 204 — a bad token is already useless."""
    try:
        payload = decode_token(body.refresh_token)
    except jwt.InvalidTokenError:
        return

    if payload.get("type") != "refresh":
        return

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if user_id and jti:
        await get_redis().delete(refresh_key(str(user_id), str(jti)))


@router.post("/reset-request", status_code=status.HTTP_204_NO_CONTENT)
async def reset_request(
    body: ResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    email = body.email.lower()
    redis = get_redis()

    # Rate limits run before the lookup so an unknown email costs the same.
    await check_rate_limit(
        redis,
        "reset-request",
        email,
        max(3, settings.AUTH_RATE_LIMIT // 3),
    )
    await check_rate_limit(
        redis, "reset-request-ip", get_client_ip(request), settings.AUTH_RATE_LIMIT
    )

    key = f"reset:{email}"
    if await redis.exists(key):
        return

    user = await _user_by_email(db, email)

    # Always return 204 — don't reveal whether email exists
    if not user or not user.is_active:
        return

    code = f"{secrets.randbelow(10**8):08d}"
    await redis.setex(key, RESET_CODE_TTL, json.dumps({"code": code, "attempts": 0}))

    try:
        await _send_sms_async(user.phone, f"Your Powerline reset code is: {code}")
    except Exception:
        log.exception("sms_send_failed", email_fingerprint=_email_fingerprint(email))
        # Still return 204 — log the failure but don't expose it


@router.post("/reset-confirm", status_code=status.HTTP_204_NO_CONTENT)
async def reset_confirm(
    body: ResetConfirm,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    redis = get_redis()
    await check_rate_limit(
        redis, "reset-confirm-ip", get_client_ip(request), settings.AUTH_RATE_LIMIT
    )

    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code"
    )

    email = body.email.lower()
    key = f"reset:{email}"
    raw = await redis.get(key)
    if not raw:
        raise invalid

    try:
        stored = json.loads(raw)
        code = str(stored["code"])
        attempts = int(stored.get("attempts", 0))
    except (TypeError, ValueError, KeyError):
        await redis.delete(key)
        raise invalid

    if not hmac.compare_digest(code.encode(), body.code.encode()):
        attempts += 1
        ttl = await redis.ttl(key)
        if attempts >= RESET_MAX_ATTEMPTS or ttl is None or ttl <= 0:
            await redis.delete(key)
            log.warning("reset_code_locked_out", email_fingerprint=_email_fingerprint(email))
        else:
            await redis.setex(key, ttl, json.dumps({"code": code, "attempts": attempts}))
        raise invalid

    user = await _user_by_email(db, email)
    if not user or not user.is_active:
        raise invalid

    user.hashed_password = hash_password(body.new_password)
    await db.commit()

    await redis.delete(key)
    await revoke_user_sessions(redis, str(user.id))
