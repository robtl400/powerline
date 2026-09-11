"""Smoke tests for auth endpoints."""

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.models.user import User

RATE_SCOPES = ("login-ip", "login-email", "reset-confirm-email", "reset-confirm-ip")


@pytest.fixture(autouse=True)
async def clean_rate_limits(redis) -> AsyncGenerator[None, None]:
    """Drop auth counters — every test client request shares one IP."""
    for scope in RATE_SCOPES:
        keys = [key async for key in redis.scan_iter(match=f"rate:{scope}:*")]
        if keys:
            await redis.delete(*keys)
    yield
    for scope in RATE_SCOPES:
        keys = [key async for key in redis.scan_iter(match=f"rate:{scope}:*")]
        if keys:
            await redis.delete(*keys)


async def test_login_returns_tokens(client: AsyncClient, admin_user: User) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "adminpass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_login_wrong_password(client: AsyncClient, admin_user: User) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.example", "password": "anything"},
    )
    assert resp.status_code == 401


async def test_refresh_returns_a_new_token_pair(
    client: AsyncClient, admin_user: User
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "adminpass123"},
    )
    refresh_token = login.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token


async def test_refresh_rejects_access_token(
    client: AsyncClient, admin_user: User
) -> None:
    """Access tokens must not be usable as refresh tokens."""
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "adminpass123"},
    )
    access_token = login.json()["access_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


async def test_get_me(client: AsyncClient, admin_user: User, admin_headers: dict) -> None:
    resp = await client.get("/api/v1/users/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == admin_user.email


async def test_get_me_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401
