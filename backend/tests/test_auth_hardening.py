"""Hardening tests for the auth and user-management endpoints.

Covers reset-code generation and lockout, rate limits, password policy,
refresh revocation, and the last-admin guard.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services.auth import hash_password

RATE_SCOPES = (
    "login-ip",
    "login-email",
    "reset-request",
    "reset-request-ip",
    "reset-confirm-email",
    "reset-confirm-ip",
)
NEW_PASSWORD = "newpassword123"
OLD_PASSWORD = "oldpassword123"
RESET_REQUEST_LIMIT = max(3, settings.AUTH_RATE_LIMIT // 3)


async def _clear_rate_keys(redis) -> None:
    for scope in RATE_SCOPES:
        keys = [key async for key in redis.scan_iter(match=f"rate:{scope}:*")]
        if keys:
            await redis.delete(*keys)


@pytest.fixture(autouse=True)
async def clean_rate_limits(redis) -> AsyncGenerator[None, None]:
    """Drop auth rate-limit counters around each test.

    The suite shares one Redis with other tests, and the IP-scoped counters
    all key off the same 127.0.0.1 test client.
    """
    await _clear_rate_keys(redis)
    yield
    await _clear_rate_keys(redis)


@pytest.fixture
async def reset_user(db: AsyncSession, redis) -> AsyncGenerator[User, None]:
    user = User(
        email=f"reset_{uuid.uuid4().hex[:8]}@test.example",
        name="Reset User",
        phone="+12025551234",
        hashed_password=hash_password(OLD_PASSWORD),
        role="staff",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    yield user
    await redis.delete(
        f"reset:{user.email.lower()}", f"reset_attempts:{user.email.lower()}"
    )
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()


@pytest.fixture
def auth_sms(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="SM_test")
    monkeypatch.setattr("app.services.sms.send_sms", mock)
    return mock


@pytest.fixture
def users_sms(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="SM_test")
    monkeypatch.setattr("app.services.sms.send_sms", mock)
    return mock


async def _stored_reset(redis, email: str) -> dict:
    raw = await redis.get(f"reset:{email.lower()}")
    assert raw is not None
    return json.loads(raw)


async def test_reset_request_stores_code_and_sends_one_sms(
    client: AsyncClient, reset_user: User, redis, auth_sms: MagicMock
) -> None:
    resp = await client.post("/api/v1/auth/reset-request", json={"email": reset_user.email})
    assert resp.status_code == 204

    stored = await _stored_reset(redis, reset_user.email)
    assert len(stored["code"]) == 8
    assert stored["code"].isdigit()

    assert auth_sms.call_count == 1
    assert stored["code"] in auth_sms.call_args.args[1]


async def test_second_reset_request_keeps_code_and_sends_nothing(
    client: AsyncClient, reset_user: User, redis, auth_sms: MagicMock
) -> None:
    await client.post("/api/v1/auth/reset-request", json={"email": reset_user.email})
    first = await _stored_reset(redis, reset_user.email)

    resp = await client.post("/api/v1/auth/reset-request", json={"email": reset_user.email})
    assert resp.status_code == 204

    second = await _stored_reset(redis, reset_user.email)
    assert second["code"] == first["code"]
    assert auth_sms.call_count == 1


async def test_reset_request_rate_limited_per_email(
    client: AsyncClient, auth_sms: MagicMock
) -> None:
    email = f"unknown_{uuid.uuid4().hex[:8]}@test.example"

    for _ in range(RESET_REQUEST_LIMIT):
        resp = await client.post("/api/v1/auth/reset-request", json={"email": email})
        assert resp.status_code == 204

    resp = await client.post("/api/v1/auth/reset-request", json={"email": email})
    assert resp.status_code == 429
    assert auth_sms.call_count == 0


async def test_reset_confirm_locks_out_after_five_wrong_codes(
    client: AsyncClient, reset_user: User, redis, auth_sms: MagicMock
) -> None:
    await client.post("/api/v1/auth/reset-request", json={"email": reset_user.email})
    code = (await _stored_reset(redis, reset_user.email))["code"]

    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/reset-confirm",
            json={"email": reset_user.email, "code": "00000000", "new_password": NEW_PASSWORD},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid or expired code"

    assert await redis.get(f"reset:{reset_user.email.lower()}") is None
    assert await redis.get(f"reset_attempts:{reset_user.email.lower()}") is None

    resp = await client.post(
        "/api/v1/auth/reset-confirm",
        json={"email": reset_user.email, "code": code, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 400

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": NEW_PASSWORD},
    )
    assert login.status_code == 401


async def test_reset_confirm_rate_limited_per_email(client: AsyncClient, redis) -> None:
    """The email counter stands on its own: clearing the IP counter does not lift it."""
    email = f"unknown_{uuid.uuid4().hex[:8]}@test.example"
    payload = {"email": email, "code": "00000000", "new_password": NEW_PASSWORD}

    async def _clear_ip_counter() -> None:
        keys = [key async for key in redis.scan_iter(match="rate:reset-confirm-ip:*")]
        if keys:
            await redis.delete(*keys)

    for _ in range(settings.AUTH_RATE_LIMIT):
        await _clear_ip_counter()
        resp = await client.post("/api/v1/auth/reset-confirm", json=payload)
        assert resp.status_code == 400

    await _clear_ip_counter()
    resp = await client.post("/api/v1/auth/reset-confirm", json=payload)
    assert resp.status_code == 429


async def test_reset_confirm_sets_new_password(
    client: AsyncClient, reset_user: User, redis, auth_sms: MagicMock
) -> None:
    await client.post("/api/v1/auth/reset-request", json={"email": reset_user.email})
    code = (await _stored_reset(redis, reset_user.email))["code"]

    resp = await client.post(
        "/api/v1/auth/reset-confirm",
        json={"email": reset_user.email, "code": code, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 204
    assert await redis.get(f"reset:{reset_user.email.lower()}") is None

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": NEW_PASSWORD},
    )
    assert login.status_code == 200

    stale = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": OLD_PASSWORD},
    )
    assert stale.status_code == 401


async def test_reset_confirm_rejects_inactive_user(
    client: AsyncClient, reset_user: User, db: AsyncSession, redis, auth_sms: MagicMock
) -> None:
    await client.post("/api/v1/auth/reset-request", json={"email": reset_user.email})
    code = (await _stored_reset(redis, reset_user.email))["code"]

    reset_user.is_active = False
    await db.commit()

    resp = await client.post(
        "/api/v1/auth/reset-confirm",
        json={"email": reset_user.email, "code": code, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 400


async def test_reset_confirm_rejects_weak_password(
    client: AsyncClient, reset_user: User, redis, auth_sms: MagicMock
) -> None:
    await client.post("/api/v1/auth/reset-request", json={"email": reset_user.email})
    code = (await _stored_reset(redis, reset_user.email))["code"]

    resp = await client.post(
        "/api/v1/auth/reset-confirm",
        json={"email": reset_user.email, "code": code, "new_password": "short1"},
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/api/v1/auth/reset-confirm",
        json={"email": reset_user.email, "code": code, "new_password": "alllettersonly"},
    )
    assert resp.status_code == 422


async def test_login_rate_limited_per_email(
    client: AsyncClient, reset_user: User, redis
) -> None:
    for _ in range(settings.AUTH_RATE_LIMIT):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": reset_user.email, "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": OLD_PASSWORD},
    )
    assert resp.status_code == 429

    keys = [key async for key in redis.scan_iter(match="rate:login-email:*")]
    assert f"rate:login-email:{reset_user.email.lower()}|127.0.0.1" in keys


async def test_login_lockout_does_not_follow_the_email_to_another_ip(
    client: AsyncClient, reset_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exhausting one IP's bucket must not lock the account out everywhere."""
    for _ in range(settings.AUTH_RATE_LIMIT):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": reset_user.email, "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": OLD_PASSWORD},
    )
    assert blocked.status_code == 429

    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "127.0.0.1/32")
    elsewhere = await client.post(
        "/api/v1/auth/login",
        headers={"X-Forwarded-For": "203.0.113.9"},
        json={"email": reset_user.email, "password": OLD_PASSWORD},
    )
    assert elsewhere.status_code == 200


async def test_refresh_rejects_deactivated_user(
    client: AsyncClient, reset_user: User, db: AsyncSession
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": OLD_PASSWORD},
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    ok = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert ok.status_code == 200

    reset_user.is_active = False
    await db.commit()

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401


async def test_create_user_rejects_invalid_role(
    client: AsyncClient, admin_headers: dict, users_sms: MagicMock
) -> None:
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": f"role_{uuid.uuid4().hex[:8]}@test.example",
            "name": "Role Test",
            "phone": "+12025551234",
            "role": "superadmin",
        },
    )
    assert resp.status_code == 422
    assert users_sms.call_count == 0


async def test_create_user_rejects_weak_password(
    client: AsyncClient, admin_headers: dict, users_sms: MagicMock
) -> None:
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": f"weak_{uuid.uuid4().hex[:8]}@test.example",
            "name": "Weak Password",
            "phone": "+12025551234",
            "password": "password",
        },
    )
    assert resp.status_code == 422
    assert users_sms.call_count == 0


async def test_create_user_rejects_non_e164_phone(
    client: AsyncClient, admin_headers: dict, users_sms: MagicMock
) -> None:
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": f"phone_{uuid.uuid4().hex[:8]}@test.example",
            "name": "Bad Phone",
            "phone": "555-1234",
        },
    )
    assert resp.status_code == 422
    assert users_sms.call_count == 0


async def test_create_user_does_not_sms_a_supplied_password(
    client: AsyncClient, admin_headers: dict, db: AsyncSession, users_sms: MagicMock
) -> None:
    password = "suppliedpass123"
    email = f"invite_{uuid.uuid4().hex[:8]}@test.example"

    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": email,
            "name": "Invited User",
            "phone": "+12025551234",
            "password": password,
        },
    )
    assert resp.status_code == 201

    try:
        assert users_sms.call_count == 1
        assert password not in users_sms.call_args.args[1]

        login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
    finally:
        await db.execute(delete(User).where(User.email == email))
        await db.commit()


async def test_create_user_conflicts_when_the_insert_loses_the_race(
    client: AsyncClient,
    admin_headers: dict,
    users_sms: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A duplicate that slips past the pre-check is caught by the unique index."""
    original_commit = AsyncSession.commit
    commits = {"count": 0}

    async def _first_commit_collides(self: AsyncSession) -> None:
        commits["count"] += 1
        if commits["count"] == 1:
            raise IntegrityError(
                "INSERT INTO users", {}, Exception("duplicate key value violates unique constraint")
            )
        await original_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", _first_commit_collides)

    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": f"race_{uuid.uuid4().hex[:8]}@test.example",
            "name": "Race Loser",
            "phone": "+12025551234",
            "password": "racedpassword123",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Email already registered"
    assert users_sms.call_count == 0


async def test_long_passwords_are_accepted_not_crashed(
    client: AsyncClient, reset_user: User, redis, auth_sms: MagicMock
) -> None:
    """bcrypt rejects inputs over 72 bytes; the policy allows up to 128 characters."""
    long_password = "l0ngpassword" * 10

    await client.post("/api/v1/auth/reset-request", json={"email": reset_user.email})
    code = (await _stored_reset(redis, reset_user.email))["code"]

    resp = await client.post(
        "/api/v1/auth/reset-confirm",
        json={"email": reset_user.email, "code": code, "new_password": long_password},
    )
    assert resp.status_code == 204

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": long_password},
    )
    assert login.status_code == 200

    wrong = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": "w0ngpassword" * 20},
    )
    assert wrong.status_code == 401


async def test_login_is_case_insensitive_on_email(
    client: AsyncClient, reset_user: User
) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email.upper(), "password": OLD_PASSWORD},
    )
    assert resp.status_code == 200


async def test_update_user_protects_the_last_admin(
    client: AsyncClient,
    admin_user: User,
    admin_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_other_admins(db: AsyncSession, user_id: uuid.UUID) -> int:
        return 0

    monkeypatch.setattr("app.api.v1.users._other_active_admins", _no_other_admins)

    demote = await client.patch(
        f"/api/v1/users/{admin_user.id}",
        headers=admin_headers,
        json={"role": "staff"},
    )
    assert demote.status_code == 409
    assert demote.json()["detail"] == "Cannot deactivate or demote the last active admin"

    deactivate = await client.patch(
        f"/api/v1/users/{admin_user.id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert deactivate.status_code == 409


async def test_update_user_allows_demotion_when_another_admin_exists(
    client: AsyncClient,
    admin_user: User,
    admin_headers: dict,
    db: AsyncSession,
) -> None:
    other = User(
        email=f"admin2_{uuid.uuid4().hex[:8]}@test.example",
        name="Second Admin",
        phone="+12025551234",
        hashed_password=hash_password("adminpass123"),
        role="admin",
    )
    db.add(other)
    await db.commit()
    await db.refresh(other)

    try:
        resp = await client.patch(
            f"/api/v1/users/{other.id}",
            headers=admin_headers,
            json={"role": "staff"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "staff"
    finally:
        await db.execute(delete(User).where(User.id == other.id))
        await db.commit()
