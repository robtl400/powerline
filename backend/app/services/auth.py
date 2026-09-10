from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

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


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "type": "access", "exp": expire},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "type": "refresh", "exp": expire},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
