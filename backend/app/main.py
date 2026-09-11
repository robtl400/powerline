import hashlib
import os
import posixpath
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.v1 import auth, calls, campaigns, health, phone_numbers, reps, tokens, users, webhooks
from app.api.v1.admin import router as admin_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.audio import router_audio, router_campaign_audio
from app.config import settings
from app.dependencies import _trusted_proxy_networks
from app.redis_client import get_redis
from app.version import __version__

log = structlog.get_logger()

_PLACEHOLDER_SECRET_KEYS = {
    "dev-secret-key-change-in-production",
    "change-me-in-production-use-openssl-rand-hex-32",
}

# The three constants below enumerate the entire public surface: the endpoints
# the embed widget calls from third-party sites, plus the embed bundle itself.
# Everything else — including the admin routes that share the
# /api/v1/campaigns/ prefix — is admin surface, so campaign paths are matched
# by exact suffix rather than by a coarse prefix.
_PUBLIC_EXACT_PATHS = ("/api/v1/calls/create", "/api/v1/tokens/voice")
_PUBLIC_PREFIXES = ("/static/",)
_PUBLIC_CAMPAIGN_SUFFIXES = ("/public", "/count", "/reps")


def _normalised_path(path: str) -> str | None:
    """Canonicalise a request path, or return None if it walks upward.

    A path carrying a `..` segment is never public: resolving it could land on
    a public suffix while the router serves an admin route, so it is refused
    outright rather than reduced.
    """
    if ".." in path.split("/"):
        return None
    collapsed = re.sub("/{2,}", "/", path)
    normalised = posixpath.normpath(collapsed)
    if collapsed.endswith("/") and not normalised.endswith("/"):
        normalised += "/"
    return normalised


def is_public_path(raw_path: str) -> bool:
    path = _normalised_path(raw_path)
    if path is None:
        return False
    if path in _PUBLIC_EXACT_PATHS or path.startswith(_PUBLIC_PREFIXES):
        return True
    return path.startswith("/api/v1/campaigns/") and path.endswith(
        _PUBLIC_CAMPAIGN_SUFFIXES
    )


def _origin_list(raw: str) -> list[str]:
    if raw.strip() == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


class PathScopedCORSMiddleware:
    """Apply one CORS policy to the public embed API and another to the admin API.

    The embed widget runs on sites we do not control, so the public endpoints
    answer any origin. The admin API is restricted to ADMIN_CORS_ORIGINS, and
    when that is empty it emits no CORS headers at all.
    """

    def __init__(self, app: ASGIApp, public_origins: list[str], admin_origins: list[str]) -> None:
        self._plain = app
        self._public = CORSMiddleware(
            app,
            allow_origins=public_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self._admin: ASGIApp = (
            CORSMiddleware(
                app,
                allow_origins=admin_origins,
                allow_credentials=False,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            if admin_origins
            else app
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._plain(scope, receive, send)
            return

        handler = self._public if is_public_path(scope["path"]) else self._admin
        await handler(scope, receive, send)


STATIC_CACHE_CONTROL = "public, max-age=300, must-revalidate"


class CachedStaticFiles(StaticFiles):
    """Serve /static with a short, revalidating cache lifetime.

    The embed bundle lives at one fixed URL, so a browser that caches it
    indefinitely keeps calling the API with a stale widget. Five minutes plus
    revalidation keeps embedding sites within one release of the API.
    """

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = STATIC_CACHE_CONTROL
        return response


def docs_enabled() -> bool:
    """Interactive docs are on when forced on, or by default in development."""
    return settings.DOCS_ENABLED is True or (
        settings.DOCS_ENABLED is None and settings.is_development
    )


def _validate_startup_config() -> None:
    """Refuse to start with an insecure configuration."""
    if settings.SECRET_KEY in _PLACEHOLDER_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY is set to a placeholder value. "
            "Generate a real one with: openssl rand -hex 32"
        )
    if len(settings.SECRET_KEY) < 32:
        raise RuntimeError(
            "SECRET_KEY must be at least 32 characters. "
            "Generate one with: openssl rand -hex 32"
        )

    try:
        ZoneInfo(settings.TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        raise RuntimeError(
            f"TIMEZONE is not a known IANA timezone name: {settings.TIMEZONE!r}. "
            "Use a name like UTC or America/New_York."
        )

    if settings.is_development:
        return

    if not _trusted_proxy_networks():
        raise RuntimeError(
            "TRUSTED_PROXIES must list at least one valid IP or CIDR in production — "
            "X-Forwarded-For is ignored without it, so every request is rate limited "
            "under the reverse proxy's own address. Set it to the subnet Caddy runs on: "
            "docker network inspect powerline_default "
            "-f '{{range .IPAM.Config}}{{.Subnet}}{{end}}'"
        )

    if not settings.TWILIO_AUTH_TOKEN:
        raise RuntimeError(
            "TWILIO_AUTH_TOKEN is required in production — "
            "webhook signature validation cannot be performed without it."
        )
    if not settings.PUBLIC_BASE_URL:
        raise RuntimeError(
            "PUBLIC_BASE_URL is required in production — "
            "Twilio webhook signature validation depends on it."
        )
    if not settings.PUBLIC_BASE_URL.startswith("https://"):
        raise RuntimeError(
            f"PUBLIC_BASE_URL must use https:// in production, got: {settings.PUBLIC_BASE_URL}"
        )
    if urlsplit(settings.PUBLIC_BASE_URL).path not in ("", "/"):
        raise RuntimeError(
            "PUBLIC_BASE_URL must carry no path, got: "
            f"{settings.PUBLIC_BASE_URL}. The webhook URLs handed to Twilio are "
            "root-absolute, so a path prefix is dropped from the callback and "
            "from the URL every signature is reconstructed over."
        )


PEPPER_FINGERPRINT_KEY = "phone_hash_pepper_fp"


def _pepper_fingerprint() -> str:
    """A short digest of the running pepper, safe to store next to the data."""
    return hashlib.sha256(settings.PHONE_HASH_PEPPER.encode()).hexdigest()[:16]


async def check_pepper_fingerprint(redis) -> None:
    """Compare the running pepper against the one the stored digests were made with.

    Every phone number is stored only as a digest under PHONE_HASH_PEPPER, so
    changing the pepper silently voids every blocklist entry and session hash
    already written. The first start records a fingerprint; a later start whose
    pepper does not match it refuses to run in production, and says so in
    development, where a throwaway database is the usual reason.

    Redis holds the fingerprint, so a Redis that is down or wiped costs the
    check rather than the boot.
    """
    current = _pepper_fingerprint()
    try:
        stored = await redis.get(PEPPER_FINGERPRINT_KEY)
    except Exception:
        log.warning("pepper_fingerprint_unavailable", exc_info=True)
        return

    if stored is None:
        try:
            await redis.set(PEPPER_FINGERPRINT_KEY, current)
        except Exception:
            log.warning("pepper_fingerprint_unavailable", exc_info=True)
        return

    if stored == current:
        return

    message = (
        "PHONE_HASH_PEPPER does not match the value this deployment's stored "
        "digests were made with. Every blocklist entry and call-session hash "
        "written under the old pepper stops matching the numbers behind it. "
        "Restore the previous pepper, or clear the "
        f"{PEPPER_FINGERPRINT_KEY} key once the stored digests have been rebuilt."
    )
    if settings.is_development:
        log.warning("phone_hash_pepper_changed", detail=message)
        return
    raise RuntimeError(message)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info(
        "powerline_api_starting",
        version=__version__,
        environment=settings.ENVIRONMENT,
    )
    _validate_startup_config()
    await check_pepper_fingerprint(get_redis())
    if not settings.GOOGLE_CIVIC_API_KEY:
        log.warning("civic_key_missing", key="GOOGLE_CIVIC_API_KEY")
    if not settings.OPENSTATES_API_KEY:
        log.warning("civic_key_missing", key="OPENSTATES_API_KEY")
    yield


def create_app() -> FastAPI:
    docs = docs_enabled()
    app = FastAPI(
        title="Powerline API",
        version=__version__,
        description="Civic activism call campaign platform",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    # JWT auth uses Authorization headers (not cookies), so credentials are
    # never needed and the two policies can both run without them.
    app.add_middleware(
        PathScopedCORSMiddleware,
        public_origins=_origin_list(settings.CORS_ORIGINS),
        admin_origins=_origin_list(settings.ADMIN_CORS_ORIGINS),
    )

    # Twilio webhooks — registered before /api/v1 routes, no auth prefix.
    app.include_router(webhooks.router, prefix="/webhooks/twilio")

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(campaigns.router, prefix="/api/v1")
    # router_campaign_audio shares the /campaigns prefix — FastAPI resolves by full path.
    app.include_router(router_campaign_audio, prefix="/api/v1")
    app.include_router(phone_numbers.router, prefix="/api/v1")
    app.include_router(router_audio, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(calls.router, prefix="/api/v1")
    app.include_router(reps.router, prefix="/api/v1")
    app.include_router(tokens.router, prefix="/api/v1")

    # Serve the built embed bundle at /static/powerline-embed.iife.js.
    # The image builds it into /app/embed-dist; docker-compose mounts embed/dist
    # over that path so a local `npm run build` is picked up without a rebuild.
    # Server starts fine either way — the bundle is optional to the API.
    embed_dist = os.environ.get("EMBED_DIST_DIR", "/app/embed-dist")
    try:
        app.mount("/static", CachedStaticFiles(directory=embed_dist), name="static")
    except RuntimeError:
        if settings.is_development:
            log.warning("embed_static_missing", directory=embed_dist)
        else:
            log.error("embed_static_missing", directory=embed_dist)

    return app


app = create_app()
