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
    RefreshOutcome,
    create_access_token,
    decode_token,
    hash_password,
    hash_password_async,
    issue_refresh_token,
    refresh_key,
    revoke_user_sessions,
    rotate_refresh_token,
    verify_password_async,
)
from app.services.digest import fingerprint
from app.services.rate_limiter import check_rate_limit
from app.services.sms import send_sms_async

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])

RESET_MAX_ATTEMPTS = 5

# Counts one wrong code and destroys the code once the attempts run out, in a
# single atomic step: parallel guesses cannot share a stale count between them.
# The counter expires with the code it guards. Returns {attempts, destroyed}.
_RESET_ATTEMPT_LUA = """
local attempts = redis.call('INCR', KEYS[2])
local ttl = redis.call('TTL', KEYS[1])
if ttl <= 0 then
    ttl = tonumber(ARGV[1])
end
if attempts >= tonumber(ARGV[2]) then
    redis.call('DEL', KEYS[1], KEYS[2])
    return {attempts, 1}
end
redis.call('EXPIRE', KEYS[2], ttl)
return {attempts, 0}
"""

# Compared against when the email is unknown so that a failed login costs the
# same time whether or not the account exists.
_DUMMY_HASH = hash_password("dummy-password")


def _reset_key(email: str) -> str:
    return f"reset:{email}"


def _reset_attempts_key(email: str) -> str:
    return f"reset_attempts:{email}"


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    """Look up an account by email, ignoring case."""
    result = await db.execute(select(User).where(func.lower(User.email) == email).limit(1))
    return result.scalars().first()


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    email = body.email.lower()
    client_ip = get_client_ip(request)
    redis = get_redis()
    await check_rate_limit(redis, "login-ip", client_ip, settings.AUTH_RATE_LIMIT * 3)
    # Keyed on the pair so a remote attacker cannot exhaust an account's bucket
    # and lock its owner out from elsewhere.
    await check_rate_limit(
        redis, "login-email", f"{email}|{client_ip}", settings.AUTH_RATE_LIMIT
    )

    user = await _user_by_email(db, email)

    if user is None:
        await verify_password_async(body.password, _DUMMY_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not await verify_password_async(body.password, user.hashed_password) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=await issue_refresh_token(redis, user_id),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> AccessTokenResponse:
    """Exchange a refresh token for a new pair, retiring the token that was used.

    Each refresh token is registered in Redis and consumed on use. For a short
    grace window after it is consumed, presenting it again returns the same
    successor token and a fresh access token, so two tabs refreshing at once
    both end up holding the live token. Past that window a second presentation
    is a replay — a stolen copy, or a token used after logout — and it ends
    every session the user has, on the assumption the chain is compromised.
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
    rotation = await rotate_refresh_token(redis, str(user.id), jti)
    if rotation.outcome is RefreshOutcome.REPLAYED:
        await revoke_user_sessions(redis, str(user.id))
        log.warning("refresh_token_replayed", user_id=str(user.id))
        raise invalid

    return AccessTokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=rotation.token,
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

    key = _reset_key(email)
    if await redis.exists(key):
        return

    user = await _user_by_email(db, email)

    # Always return 204 — don't reveal whether email exists
    if not user or not user.is_active:
        return

    code = f"{secrets.randbelow(10**8):08d}"
    await redis.delete(_reset_attempts_key(email))
    await redis.setex(key, settings.RESET_CODE_TTL_SECONDS, json.dumps({"code": code}))

    try:
        await send_sms_async(user.phone, f"Your Powerline reset code is: {code}")
    except Exception:
        log.exception("sms_send_failed", email_fingerprint=fingerprint(email))
        # Still return 204 — log the failure but don't expose it


@router.post("/reset-confirm", status_code=status.HTTP_204_NO_CONTENT)
async def reset_confirm(
    body: ResetConfirm,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    email = body.email.lower()
    redis = get_redis()

    # Rate limits run before the lookup so an unknown email costs the same.
    await check_rate_limit(redis, "reset-confirm-email", email, settings.AUTH_RATE_LIMIT)
    await check_rate_limit(
        redis, "reset-confirm-ip", get_client_ip(request), settings.AUTH_RATE_LIMIT
    )

    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code"
    )

    key = _reset_key(email)
    attempts_key = _reset_attempts_key(email)
    raw = await redis.get(key)
    if not raw:
        raise invalid

    try:
        stored = json.loads(raw)
        code = str(stored["code"])
    except (TypeError, ValueError, KeyError):
        await redis.delete(key, attempts_key)
        raise invalid

    if not hmac.compare_digest(code.encode(), body.code.encode()):
        _, destroyed = await redis.eval(
            _RESET_ATTEMPT_LUA,
            2,
            key,
            attempts_key,
            settings.RESET_CODE_TTL_SECONDS,
            RESET_MAX_ATTEMPTS,
        )
        if destroyed:
            log.warning("reset_code_locked_out", email_fingerprint=fingerprint(email))
        raise invalid

    user = await _user_by_email(db, email)
    if not user or not user.is_active:
        raise invalid

    user.hashed_password = await hash_password_async(body.new_password)
    await db.commit()

    await redis.delete(key, attempts_key)
    await revoke_user_sessions(redis, str(user.id))
