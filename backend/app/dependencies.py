import functools
import ipaddress
import uuid

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.redis_client import get_redis
from app.services.auth import decode_token, session_floor

log = structlog.get_logger()
bearer = HTTPBearer()

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@functools.lru_cache(maxsize=1)
def _parse_trusted_proxies(raw: str) -> tuple[_Network, ...]:
    """Parse a comma-separated proxy list into networks, skipping invalid entries."""
    networks: list[_Network] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            log.warning("trusted_proxy_invalid", entry=entry)
    return tuple(networks)


def _trusted_proxy_networks() -> tuple[_Network, ...]:
    from app.config import settings

    return _parse_trusted_proxies(settings.TRUSTED_PROXIES)


def _is_ip(candidate: str) -> bool:
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return True


def _is_trusted(candidate: str, networks: tuple[_Network, ...]) -> bool:
    if not networks:
        return False
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def get_client_ip(request: Request) -> str:
    """Return the client IP, honouring X-Forwarded-For only behind trusted proxies.

    The peer address is authoritative unless it belongs to a network listed in
    settings.TRUSTED_PROXIES. In that case the X-Forwarded-For chain is walked
    from the right and the first entry that parses as an address and is not
    itself a trusted proxy wins; entries that are not addresses are skipped,
    and a chain of nothing but trusted proxies falls back to the peer.
    """
    peer = request.client.host if request.client else ""
    networks = _trusted_proxy_networks()

    if not _is_trusted(peer, networks):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return peer

    for entry in reversed(forwarded.split(",")):
        entry = entry.strip()
        if not _is_ip(entry) or _is_trusted(entry, networks):
            continue
        return entry

    return peer


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    rejected = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = payload["sub"]
        issued_at = float(payload["iat"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise rejected

    # Deactivation and password resets move the user's session floor forward,
    # which retires access tokens minted before it without waiting for expiry.
    floor = await session_floor(get_redis(), user_id)
    if floor is not None and issued_at < floor:
        raise rejected

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def get_telephony_provider():
    """Return the module-level TwilioProvider singleton.

    Lazy-imports to avoid Twilio SDK initialization at startup when credentials
    may not yet be set (e.g. during test collection).
    """
    from app.services.telephony import get_provider

    return get_provider()


async def validate_twilio_request(
    request: Request,
    provider=Depends(get_telephony_provider),
) -> None:
    """Validate that an inbound webhook originated from Twilio.

    Apply this dependency to all TwiML callback endpoints. Without it,
    anyone who knows the webhook URL can trigger call logic.

    Validation is skipped only in the development environment with
    TWILIO_AUTH_TOKEN unset, so webhooks can be exercised with curl without
    real Twilio credentials. In production a missing token rejects the request.

    Note: this dependency consumes the request body stream (request.form()).
    Starlette caches the parsed form, so handlers can call request.form() again.
    """
    from app.config import settings

    if settings.is_development and not settings.TWILIO_AUTH_TOKEN:
        return

    signature = request.headers.get("X-Twilio-Signature", "")

    # Reconstruct the public URL Twilio signed — request.url reflects the
    # internal Docker address, not the public ngrok/prod hostname.
    if settings.PUBLIC_BASE_URL:
        url = settings.PUBLIC_BASE_URL.rstrip("/") + str(request.url.path)
        if request.url.query:
            url += "?" + request.url.query
    else:
        url = str(request.url)

    form_data = dict(await request.form())
    if not provider.validate_request(url, form_data, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
