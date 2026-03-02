"""Smoke tests for auth endpoints."""

from httpx import AsyncClient

from app.models.user import User


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


async def test_refresh_returns_new_access_token(
    client: AsyncClient, admin_user: User
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "adminpass123"},
    )
    refresh_token = login.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


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
