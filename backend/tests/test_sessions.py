"""Session lifecycle: refresh rotation, logout, and forced revocation."""

import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth import (
    decode_token,
    hash_password,
    refresh_grace_key,
    refresh_key,
    session_floor_key,
)

PASSWORD = "sessionpass123"
NEW_PASSWORD = "rotatedpass456"
RATE_SCOPES = (
    "login-ip",
    "login-email",
    "reset-request",
    "reset-request-ip",
    "reset-confirm-email",
    "reset-confirm-ip",
)


@pytest.fixture(autouse=True)
async def clean_rate_limits(clear_rate_keys) -> None:
    await clear_rate_keys(RATE_SCOPES)


@pytest.fixture
async def session_user(db: AsyncSession, redis) -> AsyncGenerator[User, None]:
    user = User(
        email=f"session_{uuid.uuid4().hex[:8]}@test.example",
        name="Session User",
        phone="+12025551234",
        hashed_password=hash_password(PASSWORD),
        role="staff",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    yield user

    keys: list[str] = []
    for pattern in (refresh_key(str(user.id), "*"), refresh_grace_key(str(user.id), "*")):
        keys.extend([key async for key in redis.scan_iter(match=pattern)])
    if keys:
        await redis.delete(*keys)
    await redis.delete(
        session_floor_key(str(user.id)),
        f"reset:{user.email.lower()}",
        f"reset_attempts:{user.email.lower()}",
    )
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()


async def _login(client: AsyncClient, user: User) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert resp.status_code == 200
    return resp.json()


async def test_refresh_rotates_the_token(client: AsyncClient, session_user: User) -> None:
    tokens = await _login(client, session_user)

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200
    rotated = first.json()["refresh_token"]
    assert rotated != tokens["refresh_token"]

    still_good = await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated})
    assert still_good.status_code == 200


async def test_second_refresh_inside_the_grace_window_gets_the_same_successor(
    client: AsyncClient, session_user: User
) -> None:
    """Two tabs refreshing at once must not leave one of them holding a dead token."""
    tokens = await _login(client, session_user)

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    second = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200
    assert second.status_code == 200

    successor = first.json()["refresh_token"]
    assert second.json()["refresh_token"] == successor
    assert second.json()["access_token"] != first.json()["access_token"]

    headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 200

    still_good = await client.post("/api/v1/auth/refresh", json={"refresh_token": successor})
    assert still_good.status_code == 200


async def test_replay_after_the_grace_window_ends_every_session(
    client: AsyncClient, session_user: User, redis
) -> None:
    """A replayed jti means the chain is stolen, so every session for the user dies."""
    tokens = await _login(client, session_user)
    jti = decode_token(tokens["refresh_token"])["jti"]

    rotation = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotation.status_code == 200
    successor = rotation.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {rotation.json()['access_token']}"}
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 200

    await redis.delete(refresh_grace_key(str(session_user.id), jti))

    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": successor})
    ).status_code == 401
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401


async def test_refresh_rejects_a_token_never_registered(
    client: AsyncClient, session_user: User, redis
) -> None:
    """A validly signed refresh token is useless once its jti is gone."""
    tokens = await _login(client, session_user)
    keys = [key async for key in redis.scan_iter(match=refresh_key(str(session_user.id), "*"))]
    await redis.delete(*keys)

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


async def test_logout_invalidates_the_refresh_token(
    client: AsyncClient, session_user: User
) -> None:
    tokens = await _login(client, session_user)

    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout.status_code == 204

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


async def test_logout_is_quiet_about_junk_tokens(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "not-a-jwt"})
    assert resp.status_code == 204


async def test_deactivation_kills_refresh_and_access_tokens(
    client: AsyncClient,
    session_user: User,
    admin_headers: dict,
) -> None:
    tokens = await _login(client, session_user)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200

    deactivate = await client.patch(
        f"/api/v1/users/{session_user.id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert deactivate.status_code == 200

    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 401


async def test_role_change_kills_outstanding_access_tokens(
    client: AsyncClient,
    session_user: User,
    admin_headers: dict,
) -> None:
    tokens = await _login(client, session_user)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 200

    promote = await client.patch(
        f"/api/v1/users/{session_user.id}",
        headers=admin_headers,
        json={"role": "admin"},
    )
    assert promote.status_code == 200

    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401


async def test_password_reset_kills_outstanding_access_tokens(
    client: AsyncClient,
    session_user: User,
    redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.sms.send_sms", MagicMock(return_value="SM_test"))

    tokens = await _login(client, session_user)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 200

    await client.post("/api/v1/auth/reset-request", json={"email": session_user.email})
    code = json.loads(await redis.get(f"reset:{session_user.email.lower()}"))["code"]

    confirm = await client.post(
        "/api/v1/auth/reset-confirm",
        json={
            "email": session_user.email,
            "code": code,
            "new_password": NEW_PASSWORD,
        },
    )
    assert confirm.status_code == 204

    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401


async def test_users_list_honours_skip_and_limit(
    client: AsyncClient, admin_headers: dict, session_user: User
) -> None:
    full = await client.get("/api/v1/users?limit=500", headers=admin_headers)
    assert full.status_code == 200
    assert len(full.json()["items"]) >= 2
    assert full.json()["total"] >= 2

    first = await client.get("/api/v1/users?limit=1", headers=admin_headers)
    assert first.status_code == 200
    assert len(first.json()["items"]) == 1
    assert first.json()["total"] == full.json()["total"]

    second = await client.get("/api/v1/users?skip=1&limit=1", headers=admin_headers)
    assert second.status_code == 200
    assert second.json()["items"][0]["id"] != first.json()["items"][0]["id"]

    assert (
        await client.get("/api/v1/users?limit=501", headers=admin_headers)
    ).status_code == 422


async def test_phone_numbers_list_accepts_pagination(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.get("/api/v1/phone-numbers?skip=0&limit=1", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) <= 1

    assert (
        await client.get("/api/v1/phone-numbers?limit=0", headers=admin_headers)
    ).status_code == 422
