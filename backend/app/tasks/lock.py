"""Redis lock for periodic tasks.

Beat fires on a schedule regardless of whether the previous run finished, so
long-running tasks need a lock to avoid two workers doing the same work.
The primitive itself lives in app.services.redis_lock, shared with the request
handlers; this module adds the context manager the tasks use.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.services.redis_lock import RELEASE_IF_OWNER, acquire, release

__all__ = ["RELEASE_IF_OWNER", "acquire", "release", "task_lock"]


@contextmanager
def task_lock(client: Any, key: str, ttl: int) -> Iterator[bool]:
    """Yield whether the lock was taken, releasing it on the way out."""
    token = acquire(client, key, ttl)
    try:
        yield token is not None
    finally:
        if token is not None:
            release(client, key, token)
