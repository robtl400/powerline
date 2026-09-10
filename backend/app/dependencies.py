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
from app.services.auth import decode_token

log = structlog.get_logger()
bearer = HTTPBearer()

_trusted_proxy_cache: tuple[str, list[ipaddress.IPv4Network | ipaddress.IPv6Network]] | None = None


def _trusted_proxy_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse settings.TRUSTED_PROXIES into networks, cached on the raw string."""
    global _trusted_proxy_cache

    from app.config import settings

    raw = settings.TRUSTED_PROXIES
    if _trusted_proxy_cache is not None and _trusted_proxy_cache[0] == raw:
        return _trusted_proxy_cache[1]

    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            log.warning("trusted_proxy_invalid", entry=entry)

    _trusted_proxy_cache = (raw, networks)
    return networks


def _is_trusted(candidate: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
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
    from the right and the first entry that is not itself a trusted proxy wins.
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
        if not entry or _is_trusted(entry, networks):
            continue
        return entry

    return peer


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = payload["sub"]
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
