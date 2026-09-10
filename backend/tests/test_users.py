"""User management endpoints: list, create, and update.

Password policy, role validation, and the last-admin guard live in
test_auth_hardening; session revocation on deactivation lives in test_sessions.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

RATE_SCOPES = ("login-ip", "login-email")


@pytest.fixture(autouse=True)
async def clean_login_limits(redis) -> AsyncGenerator[None, None]:
    """Drop login counters — every test client request shares one IP."""
    for scope in RATE_SCOPES:
        keys = [key async for key in redis.scan_iter(match=f"rate:{scope}:*")]
        if keys:
            await redis.delete(*keys)
    yield
    for scope in RATE_SCOPES:
        keys = [key async for key in redis.scan_iter(match=f"rate:{scope}:*")]
        if keys:
            await redis.delete(*keys)


@pytest.fixture
def users_sms(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="SM_test")
    monkeypatch.setattr("app.api.v1.users.send_sms", mock)
    return mock


@pytest.fixture
async def new_email(db: AsyncSession) -> AsyncGenerator[Callable[[], str], None]:
    """Hand out unique test emails and delete whatever was created under them."""
    issued: list[str] = []

    def _issue() -> str:
        email = f"user_{uuid.uuid4().hex[:10]}@test.example"
        issued.append(email)
        return email

    yield _issue

    if issued:
        await db.execute(delete(User).where(User.email.in_(issued)))
        await db.commit()


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------


async def test_list_users_returns_the_caller(
    client: AsyncClient, admin_user: User, admin_headers: dict
) -> None:
    resp = await client.get("/api/v1/users", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert str(admin_user.id) in [u["id"] for u in body]
    assert all("hashed_password" not in u for u in body)


async def test_list_users_is_admin_only(client: AsyncClient, staff_headers: dict) -> None:
    resp = await client.get("/api/v1/users", headers=staff_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------


async def test_create_user_sms_a_working_temporary_password(
    client: AsyncClient,
    admin_headers: dict,
    users_sms: MagicMock,
    new_email: Callable[[], str],
) -> None:
    """With no password supplied, one SMS carries a password that actually signs in."""
    email = new_email()
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={"email": email, "name": "Temp Password", "phone": "+12025553100"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "staff"
    assert resp.json()["is_active"] is True

    assert users_sms.call_count == 1
    to, body = users_sms.call_args.args
    assert to == "+12025553100"
    temp_password = body.rsplit(": ", 1)[1]

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": temp_password}
    )
    assert login.status_code == 200, login.text


async def test_create_user_accepts_an_explicit_role(
    client: AsyncClient,
    admin_headers: dict,
    users_sms: MagicMock,
    new_email: Callable[[], str],
) -> None:
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": new_email(),
            "name": "Second Admin",
            "phone": "+12025553101",
            "password": "explicitpass123",
            "role": "admin",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "admin"


async def test_create_user_rejects_a_duplicate_email(
    client: AsyncClient,
    admin_headers: dict,
    users_sms: MagicMock,
    new_email: Callable[[], str],
) -> None:
    email = new_email()
    payload = {
        "email": email,
        "name": "First",
        "phone": "+12025553102",
        "password": "duplicatepass123",
    }
    first = await client.post("/api/v1/users", headers=admin_headers, json=payload)
    assert first.status_code == 201, first.text

    again = await client.post("/api/v1/users", headers=admin_headers, json=payload)
    assert again.status_code == 409
    assert again.json()["detail"] == "Email already registered"


async def test_create_user_rejects_a_duplicate_email_in_another_case(
    client: AsyncClient,
    admin_headers: dict,
    users_sms: MagicMock,
    new_email: Callable[[], str],
) -> None:
    """Emails are stored lowercased, so casing cannot smuggle in a second account."""
    email = new_email()
    first = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": email,
            "name": "Lower",
            "phone": "+12025553103",
            "password": "casingpass123",
        },
    )
    assert first.status_code == 201, first.text

    again = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": email.upper(),
            "name": "Upper",
            "phone": "+12025553104",
            "password": "casingpass123",
        },
    )
    assert again.status_code == 409


async def test_create_user_is_admin_only(
    client: AsyncClient, staff_headers: dict, users_sms: MagicMock
) -> None:
    resp = await client.post(
        "/api/v1/users",
        headers=staff_headers,
        json={
            "email": f"staffmade_{uuid.uuid4().hex[:8]}@test.example",
            "name": "Staff Attempt",
            "phone": "+12025553105",
            "password": "staffmadepass123",
        },
    )
    assert resp.status_code == 403
    assert users_sms.call_count == 0


# ---------------------------------------------------------------------------
# PATCH /users/{id}
# ---------------------------------------------------------------------------


async def test_update_user_writes_every_editable_field(
    client: AsyncClient,
    db: AsyncSession,
    staff_user: User,
    admin_headers: dict,
) -> None:
    resp = await client.patch(
        f"/api/v1/users/{staff_user.id}",
        headers=admin_headers,
        json={
            "name": "Renamed Staff",
            "phone": "+1 (202) 555-3106",
            "role": "admin",
            "is_active": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Renamed Staff"
    assert body["phone"] == "+12025553106"
    assert body["role"] == "admin"
    assert body["is_active"] is False

    stored = await db.scalar(select(User).where(User.id == staff_user.id))
    await db.refresh(stored)
    assert stored.name == "Renamed Staff"
    assert stored.role == "admin"
    assert stored.is_active is False


async def test_update_user_leaves_unsent_fields_alone(
    client: AsyncClient, staff_user: User, admin_headers: dict
) -> None:
    resp = await client.patch(
        f"/api/v1/users/{staff_user.id}",
        headers=admin_headers,
        json={"name": "Only The Name"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Only The Name"
    assert body["role"] == "staff"
    assert body["phone"] == staff_user.phone
    assert body["is_active"] is True


async def test_update_user_rejects_a_bad_phone(
    client: AsyncClient, staff_user: User, admin_headers: dict
) -> None:
    resp = await client.patch(
        f"/api/v1/users/{staff_user.id}",
        headers=admin_headers,
        json={"phone": "555-3107"},
    )
    assert resp.status_code == 422


async def test_update_unknown_user_is_404(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.patch(
        f"/api/v1/users/{uuid.uuid4()}", headers=admin_headers, json={"name": "Ghost"}
    )
    assert resp.status_code == 404


async def test_update_user_is_admin_only(
    client: AsyncClient, staff_user: User, staff_headers: dict
) -> None:
    resp = await client.patch(
        f"/api/v1/users/{staff_user.id}",
        headers=staff_headers,
        json={"name": "Self Promotion"},
    )
    assert resp.status_code == 403
