"""Startup configuration guard, the pepper fingerprint, and the /static cache policy."""

import os
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import app.config
import app.main
from app.main import (
    PEPPER_FINGERPRINT_KEY,
    STATIC_CACHE_CONTROL,
    _validate_startup_config,
    check_pepper_fingerprint,
)
from app.main import app as fastapi_app

_GOOD_SECRET = "a" * 64


def _settings(**overrides) -> SimpleNamespace:
    """A production-ready settings stub, before overrides are applied."""
    base = {
        "SECRET_KEY": _GOOD_SECRET,
        "TIMEZONE": "UTC",
        "is_development": False,
        "TRUSTED_PROXIES": "172.18.0.0/16",
        "TWILIO_AUTH_TOKEN": "token",
        "PUBLIC_BASE_URL": "https://powerline.example.com",
        "PHONE_HASH_PEPPER": "pepper-in-use",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def configure(monkeypatch):
    """Install a settings stub everywhere the startup check reads it from."""

    def install(**overrides) -> SimpleNamespace:
        stub = _settings(**overrides)
        monkeypatch.setattr(app.main, "settings", stub)
        monkeypatch.setattr(app.config, "settings", stub)
        return stub

    return install


def test_fully_configured_production_passes(configure) -> None:
    configure()
    _validate_startup_config()


def test_placeholder_secret_key_rejected(configure) -> None:
    configure(SECRET_KEY="change-me-in-production-use-openssl-rand-hex-32")
    with pytest.raises(RuntimeError, match="placeholder"):
        _validate_startup_config()


def test_short_secret_key_rejected(configure) -> None:
    configure(SECRET_KEY="tooshort")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        _validate_startup_config()


def test_unknown_timezone_rejected(configure) -> None:
    configure(TIMEZONE="Mars/Olympus_Mons")
    with pytest.raises(RuntimeError, match="TIMEZONE"):
        _validate_startup_config()


def test_unknown_timezone_rejected_in_development(configure) -> None:
    configure(is_development=True, TIMEZONE="Mars/Olympus_Mons")
    with pytest.raises(RuntimeError, match="TIMEZONE"):
        _validate_startup_config()


def test_missing_twilio_auth_token_rejected(configure) -> None:
    configure(TWILIO_AUTH_TOKEN="")
    with pytest.raises(RuntimeError, match="TWILIO_AUTH_TOKEN"):
        _validate_startup_config()


def test_missing_public_base_url_rejected(configure) -> None:
    configure(PUBLIC_BASE_URL="")
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL is required"):
        _validate_startup_config()


def test_non_https_public_base_url_rejected(configure) -> None:
    configure(PUBLIC_BASE_URL="http://powerline.example.com")
    with pytest.raises(RuntimeError, match="must use https"):
        _validate_startup_config()


@pytest.mark.parametrize(
    "url",
    [
        "https://powerline.example.com/powerline",
        "https://powerline.example.com/api/",
    ],
)
def test_public_base_url_with_a_path_rejected(configure, url) -> None:
    configure(PUBLIC_BASE_URL=url)
    with pytest.raises(RuntimeError, match="must carry no path"):
        _validate_startup_config()


def test_public_base_url_may_end_in_a_slash(configure) -> None:
    configure(PUBLIC_BASE_URL="https://powerline.example.com/")
    _validate_startup_config()


def test_empty_trusted_proxies_rejected(configure) -> None:
    configure(TRUSTED_PROXIES="")
    with pytest.raises(RuntimeError, match="TRUSTED_PROXIES"):
        _validate_startup_config()


def test_unparseable_trusted_proxies_rejected(configure) -> None:
    configure(TRUSTED_PROXIES="not-an-address, also-not-one")
    with pytest.raises(RuntimeError, match="TRUSTED_PROXIES"):
        _validate_startup_config()


@pytest.mark.parametrize(
    "overrides",
    [
        {"TRUSTED_PROXIES": ""},
        {"TWILIO_AUTH_TOKEN": ""},
        {"PUBLIC_BASE_URL": ""},
        {"PUBLIC_BASE_URL": "http://localhost:8000"},
    ],
)
def test_development_skips_production_checks(configure, overrides) -> None:
    configure(is_development=True, **overrides)
    _validate_startup_config()


# ---------------------------------------------------------------------------
# PHONE_HASH_PEPPER fingerprint
# ---------------------------------------------------------------------------


class _FakeRedis:
    """The two calls the fingerprint check makes, over a dict."""

    def __init__(self, stored: dict | None = None) -> None:
        self.store = dict(stored or {})

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str) -> None:
        self.store[key] = value


class _DeadRedis(_FakeRedis):
    async def get(self, key: str):
        raise ConnectionError("redis is down")

    async def set(self, key: str, value: str) -> None:
        raise ConnectionError("redis is down")


async def test_first_start_records_the_pepper_fingerprint(configure) -> None:
    configure()
    redis = _FakeRedis()

    await check_pepper_fingerprint(redis)

    assert redis.store[PEPPER_FINGERPRINT_KEY] == app.main._pepper_fingerprint()


async def test_matching_pepper_passes(configure) -> None:
    configure()
    redis = _FakeRedis({PEPPER_FINGERPRINT_KEY: app.main._pepper_fingerprint()})

    await check_pepper_fingerprint(redis)

    assert redis.store[PEPPER_FINGERPRINT_KEY] == app.main._pepper_fingerprint()


async def test_changed_pepper_refuses_to_start_in_production(configure) -> None:
    configure()
    redis = _FakeRedis({PEPPER_FINGERPRINT_KEY: "0123456789abcdef"})

    with pytest.raises(RuntimeError, match="PHONE_HASH_PEPPER"):
        await check_pepper_fingerprint(redis)


async def test_changed_pepper_only_warns_in_development(configure) -> None:
    configure(is_development=True)
    redis = _FakeRedis({PEPPER_FINGERPRINT_KEY: "0123456789abcdef"})

    await check_pepper_fingerprint(redis)

    assert redis.store[PEPPER_FINGERPRINT_KEY] == "0123456789abcdef"


async def test_pepper_check_is_skipped_when_redis_is_unreachable(configure) -> None:
    """A Redis that is down costs the check, not the boot."""
    configure()

    await check_pepper_fingerprint(_DeadRedis())


_embed_dist = os.environ.get("EMBED_DIST_DIR", "/app/embed-dist")
_bundle = os.path.join(_embed_dist, "powerline-embed.iife.js")


@pytest.mark.asyncio
@pytest.mark.skipif(not os.path.exists(_bundle), reason="embed bundle not built")
async def test_static_bundle_is_cached_briefly() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        response = await client.get("/static/powerline-embed.iife.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == STATIC_CACHE_CONTROL
