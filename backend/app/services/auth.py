import asyncio
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import TYPE_CHECKING

import bcrypt
import jwt

from app.config import settings

if TYPE_CHECKING:
    from redis.asyncio import Redis

ALGORITHM = "HS256"

# How long a consumed refresh token keeps answering with its successor, so two
# tabs refreshing at the same moment are not mistaken for a stolen token.
REFRESH_GRACE_SECONDS = 30

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
BCRYPT_MAX_BYTES = 72
PASSWORD_POLICY_MESSAGE = (
    "Password must be at least 12 characters and include a letter and a number"
)


def validate_password_strength(v: str) -> str:
    """Return the password unchanged, or raise ValueError when it fails the policy.

    Shared by every schema that accepts a new password so the rules live in
    one place: 12–128 characters, at least one letter and at least one digit.
    """
    if not PASSWORD_MIN_LENGTH <= len(v) <= PASSWORD_MAX_LENGTH:
        raise ValueError(PASSWORD_POLICY_MESSAGE)
    if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        raise ValueError(PASSWORD_POLICY_MESSAGE)
    return v


def _bcrypt_input(password: str) -> bytes:
    """Encode a password for bcrypt, which rejects inputs over 72 bytes."""
    return password.encode()[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_bcrypt_input(plain), hashed.encode())


async def hash_password_async(password: str) -> str:
    """Hash off the event loop — bcrypt burns ~100ms of CPU per call."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    """Verify off the event loop — bcrypt burns ~100ms of CPU per call."""
    return await asyncio.to_thread(verify_password, plain, hashed)


def refresh_token_ttl() -> int:
    """Refresh-token lifetime in seconds."""
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400


def refresh_key(user_id: str, jti: str) -> str:
    return f"refresh:{user_id}:{jti}"


def refresh_grace_key(user_id: str, jti: str) -> str:
    return f"refresh_grace:{user_id}:{jti}"


def session_floor_key(user_id: str) -> str:
    return f"session_floor:{user_id}"


def _encode(user_id: str, token_type: str, lifetime: timedelta) -> str:
    """Sign a token carrying a unique jti and a sub-second issue time.

    `iat` is stored as a float so a revocation marker written moments after a
    token was minted still sorts after it — integer seconds are too coarse to
    tell "issued just before the revocation" from "issued just after".
    """
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "type": token_type,
            "jti": secrets.token_urlsafe(16),
            "iat": now.timestamp(),
            "exp": now + lifetime,
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def create_access_token(user_id: str) -> str:
    return _encode(
        user_id, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(user_id: str) -> str:
    return _encode(
        user_id, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


async def issue_refresh_token(redis: "Redis", user_id: str) -> str:
    """Mint a refresh token and register its jti so it can be used exactly once."""
    token = create_refresh_token(user_id)
    jti = decode_token(token)["jti"]
    await redis.setex(refresh_key(user_id, jti), refresh_token_ttl(), "1")
    return token


class RefreshOutcome(StrEnum):
    """What presenting a refresh token's jti turned out to be."""

    CONSUMED = "consumed"
    GRACE = "grace"
    REPLAYED = "replayed"


@dataclass(frozen=True)
class RefreshRotation:
    """The result of rotating a refresh token; `token` is None on a replay."""

    outcome: RefreshOutcome
    token: str | None = None


# Retires the presented jti and records its successor, or reports what the jti
# already is. Runs as one atomic step so two simultaneous presentations cannot
# both see an unconsumed jti, and so a concurrent second presentation never
# lands in the gap between the delete and the grace marker.
_ROTATE_LUA = """
if redis.call('DEL', KEYS[1]) == 1 then
    redis.call('SETEX', KEYS[2], ARGV[2], ARGV[1])
    return {'consumed', ''}
end
local successor = redis.call('GET', KEYS[2])
if successor then
    return {'grace', successor}
end
return {'replayed', ''}
"""


async def rotate_refresh_token(redis: "Redis", user_id: str, jti: str) -> RefreshRotation:
    """Retire a presented refresh jti and return the token that replaces it.

    A jti that was still registered is consumed and its successor is recorded
    under a short grace window; presenting the same jti again inside that
    window hands back the same successor, which is what a second browser tab
    racing the first one needs. A jti that is neither registered nor inside its
    grace window is a replay.
    """
    successor = create_refresh_token(user_id)
    successor_jti = decode_token(successor)["jti"]
    await redis.setex(refresh_key(user_id, successor_jti), refresh_token_ttl(), "1")

    outcome, recorded = await redis.eval(
        _ROTATE_LUA,
        2,
        refresh_key(user_id, jti),
        refresh_grace_key(user_id, jti),
        successor,
        REFRESH_GRACE_SECONDS,
    )

    if outcome == RefreshOutcome.CONSUMED:
        return RefreshRotation(RefreshOutcome.CONSUMED, successor)

    await redis.delete(refresh_key(user_id, successor_jti))

    if outcome == RefreshOutcome.GRACE:
        return RefreshRotation(RefreshOutcome.GRACE, recorded)
    return RefreshRotation(RefreshOutcome.REPLAYED)


async def revoke_user_sessions(redis: "Redis", user_id: str) -> None:
    """End every session for a user: refresh tokens and outstanding access tokens.

    The session floor is compared against each access token's `iat`, so tokens
    already in the wild stop working without waiting for their expiry. Grace
    markers go with the refresh tokens, so no retired jti can still hand out a
    successor once the sessions behind it are gone.
    """
    keys: list[str] = []
    for pattern in (refresh_key(user_id, "*"), refresh_grace_key(user_id, "*")):
        keys.extend([key async for key in redis.scan_iter(match=pattern)])
    if keys:
        await redis.delete(*keys)
    floor = datetime.now(timezone.utc).timestamp()
    await redis.setex(session_floor_key(user_id), refresh_token_ttl(), repr(floor))


async def session_floor(redis: "Redis", user_id: str) -> float | None:
    """Return the timestamp before which this user's access tokens are dead."""
    raw = await redis.get(session_floor_key(user_id))
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
