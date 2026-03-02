from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import auth, calls, campaigns, health, phone_numbers, tokens, users, webhooks
from app.api.v1.admin import router as admin_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.audio import router_audio, router_campaign_audio
from app.config import settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("powerline_api_starting", version="2.0.0-dev")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Powerline API",
        version="2.0.0-dev",
        description="Civic activism call campaign platform",
        lifespan=lifespan,
    )

    # CORS — allow_origins from env (defaults to "*").
    # JWT auth uses Authorization headers (not cookies) so credentials not needed.
    # The embed widget runs on third-party sites, so "*" is correct for the public API.
    cors_origins = (
        [o.strip() for o in settings.CORS_ORIGINS.split(",")]
        if settings.CORS_ORIGINS != "*"
        else ["*"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
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
    app.include_router(tokens.router, prefix="/api/v1")

    # Serve the built embed bundle at /static/powerline-embed.iife.js.
    # The embed/dist directory is volume-mounted at /app/embed-dist in docker-compose.
    # Server starts fine even if the directory is empty or the build hasn't run yet.
    try:
        app.mount("/static", StaticFiles(directory="/app/embed-dist"), name="static")
    except RuntimeError:
        log.warning("embed_static_not_mounted", reason="embed/dist directory not found or empty")

    return app


app = create_app()
