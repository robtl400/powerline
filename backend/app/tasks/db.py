"""Shared synchronous resources for Celery tasks.

Celery workers run in a sync context, so tasks cannot use the app's asyncpg
engine or the async Redis client. The engine and Redis client here are built
once per worker process and reused by every task run — creating them per run
leaks connection pools.
"""
from __future__ import annotations

import redis
from sqlalchemy import Engine, create_engine

from app.config import settings
from app.redis_client import connection_kwargs

_engine: Engine | None = None
_redis: redis.Redis | None = None


def sync_database_url() -> str:
    """Translate the asyncpg DATABASE_URL into its psycopg2 equivalent."""
    url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(sync_database_url(), pool_pre_ping=True)
    return _engine


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(
            settings.REDIS_URL,
            **connection_kwargs(settings.REDIS_URL, settings.REDIS_PASSWORD),
        )
    return _redis
