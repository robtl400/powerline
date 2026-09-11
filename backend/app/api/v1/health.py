from fastapi import APIRouter

from app.config import settings
from app.version import __version__

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "default_rate_limit": settings.DEFAULT_RATE_LIMIT,
    }
