"""A Redis key one holder owns for a bounded time.

Both halves of the app take the same kind of lock: Celery tasks through the
sync client, request handlers through the async one. The Lua script and the
token discipline live here so the two cannot drift apart.

A lock is released only by its owner: a holder that overran its TTL must not
delete the key a later holder is now using. A holder that expects to outlive
its TTL refreshes it instead, which is also owner-checked.
"""
from __future__ import annotations

import secrets
from typing import Any

RELEASE_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

REFRESH_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""


def new_token() -> str:
    """A fresh owner token, unguessable by another holder."""
    return secrets.token_urlsafe(16)


def acquire(client: Any, key: str, ttl: int) -> str | None:
    """Take the lock, returning the owner token, or None when already held."""
    token = new_token()
    if client.set(key, token, nx=True, ex=ttl):
        return token
    return None


def release(client: Any, key: str, token: str) -> bool:
    """Release the lock only when this token still owns it."""
    return bool(client.eval(RELEASE_IF_OWNER, 1, key, token))


async def acquire_async(client: Any, key: str, ttl: int) -> str | None:
    """Take the lock, returning the owner token, or None when already held."""
    token = new_token()
    if await client.set(key, token, nx=True, ex=ttl):
        return token
    return None


async def release_async(client: Any, key: str, token: str) -> bool:
    """Release the lock only when this token still owns it."""
    return bool(await client.eval(RELEASE_IF_OWNER, 1, key, token))


async def refresh_async(client: Any, key: str, token: str, ttl: int) -> bool:
    """Extend the lock to a full TTL again, only while this token owns it."""
    return bool(await client.eval(REFRESH_IF_OWNER, 1, key, token, ttl))
