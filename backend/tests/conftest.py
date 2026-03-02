"""Shared test fixtures."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.redis_client as _redis_module
from app.config import settings
from app.db import get_db
from app.dependencies import validate_twilio_request
from app.main import app
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.models.user import User
from app.services.auth import create_access_token, hash_password

# NullPool avoids reusing asyncpg connections across test functions. Each test
# function gets its own event loop (pytest-asyncio default), and asyncpg
# connections are bound to the loop they were created on. NullPool forces a
# fresh connection per session, preventing "another operation in progress" errors.
_test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
_TestSession = async_sessionmaker(_test_engine, expire_on_commit=False)


async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSession() as session:
        yield session


# Override the app's DB dependency so all HTTP requests also use NullPool,
# preventing asyncpg connections from being reused across event loops.
app.dependency_overrides[get_db] = _get_test_db


async def _skip_twilio_validation() -> None:
    """No-op override for validate_twilio_request in tests.

    When real Twilio credentials are in .env, the signature check would fail
    on every test webhook request. Override it to bypass, the same pattern as
    overriding get_db with the test session.
    """


app.dependency_overrides[validate_twilio_request] = _skip_twilio_validation


@pytest.fixture(autouse=True)
async def reset_redis() -> AsyncGenerator[None, None]:
    """Reset the Redis singleton before each test.

    get_redis() returns a module-level singleton whose underlying connection
    is bound to the event loop that created it. pytest-asyncio creates a new
    event loop per test function, so we must create a fresh client for each
    test — otherwise the second test hits 'Event loop is closed'.
    """
    _redis_module._redis = None
    yield
    if _redis_module._redis is not None:
        await _redis_module._redis.aclose()
    _redis_module._redis = None


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSession() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def admin_user(db: AsyncSession) -> AsyncGenerator[User, None]:
    user = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@test.example",
        name="Test Admin",
        phone="+15550000001",
        hashed_password=hash_password("adminpass123"),
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    yield user
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()


@pytest.fixture
async def staff_user(db: AsyncSession) -> AsyncGenerator[User, None]:
    user = User(
        email=f"staff_{uuid.uuid4().hex[:8]}@test.example",
        name="Test Staff",
        phone="+15550000002",
        hashed_password=hash_password("staffpass123"),
        role="staff",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    yield user
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()


@pytest.fixture
def admin_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(str(admin_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def staff_headers(staff_user: User) -> dict[str, str]:
    token = create_access_token(str(staff_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def campaign(
    db: AsyncSession, admin_user: User
) -> AsyncGenerator[Campaign, None]:
    c = Campaign(
        name=f"Test Campaign {uuid.uuid4().hex[:8]}",
        created_by_id=admin_user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    yield c
    await db.execute(delete(CampaignTarget).where(CampaignTarget.campaign_id == c.id))
    await db.execute(delete(Campaign).where(Campaign.id == c.id))
    await db.commit()
