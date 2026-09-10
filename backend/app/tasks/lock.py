"""Redis lock for periodic tasks.

Beat fires on a schedule regardless of whether the previous run finished, so
long-running tasks need a lock to avoid two workers doing the same work. The
lock is released only by its owner: a run that overran its TTL must not delete
the lock a later run is holding.
"""
from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_RELEASE_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def acquire(client: Any, key: str, ttl: int) -> str | None:
    """Take the lock, returning the owner token, or None when already held."""
    token = secrets.token_urlsafe(16)
    if client.set(key, token, nx=True, ex=ttl):
        return token
    return None


def release(client: Any, key: str, token: str) -> bool:
    """Release the lock only when this token still owns it."""
    return bool(client.eval(_RELEASE_IF_OWNER, 1, key, token))


@contextmanager
def task_lock(client: Any, key: str, ttl: int) -> Iterator[bool]:
    """Yield whether the lock was taken, releasing it on the way out."""
    token = acquire(client, key, ttl)
    try:
        yield token is not None
    finally:
        if token is not None:
            release(client, key, token)
