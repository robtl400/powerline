"""Twilio webhook signature validation.

conftest installs a global no-op override for validate_twilio_request so the
rest of the suite can POST webhooks freely. This module pops that override so
the real dependency runs, and feeds it a provider whose validate_request is a
real twilio RequestValidator keyed to a known token.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from twilio.request_validator import RequestValidator

from app.config import settings
from app.dependencies import get_telephony_provider, validate_twilio_request
from app.main import app

AUTH_TOKEN = "test-auth-token"
BASE_URL = "https://example.test"
VOICE_APP = "/webhooks/twilio/voice-app"


def _signature(path: str, form: dict[str, str], query: str = "", token: str = AUTH_TOKEN) -> str:
    """Sign exactly the URL dependencies.validate_twilio_request reconstructs."""
    url = BASE_URL + path
    if query:
        url += "?" + query
    return RequestValidator(token).compute_signature(url, form)


def _validating_provider(token: str = AUTH_TOKEN) -> MagicMock:
    provider = MagicMock()
    provider.validate_request.side_effect = (
        lambda url, post_vars, signature: RequestValidator(token).validate(
            url, post_vars, signature
        )
    )
    return provider


@pytest.fixture
async def enforced(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None, None]:
    """Run the real signature check for this test, then restore the suite default."""
    skip_override = app.dependency_overrides.pop(validate_twilio_request)
    app.dependency_overrides[get_telephony_provider] = _validating_provider

    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", BASE_URL)

    yield

    app.dependency_overrides.pop(get_telephony_provider, None)
    app.dependency_overrides[validate_twilio_request] = skip_override


# ---------------------------------------------------------------------------
# Production: the signature decides
# ---------------------------------------------------------------------------


async def test_missing_signature_is_rejected(client: AsyncClient, enforced: None) -> None:
    resp = await client.post(VOICE_APP, data={"CallSid": "CAsig0001"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Invalid Twilio signature"


async def test_garbage_signature_is_rejected(client: AsyncClient, enforced: None) -> None:
    resp = await client.post(
        VOICE_APP,
        data={"CallSid": "CAsig0002"},
        headers={"X-Twilio-Signature": "not-a-signature"},
    )
    assert resp.status_code == 403


async def test_signature_from_a_different_token_is_rejected(
    client: AsyncClient, enforced: None
) -> None:
    form = {"CallSid": "CAsig0003"}
    resp = await client.post(
        VOICE_APP,
        data=form,
        headers={"X-Twilio-Signature": _signature(VOICE_APP, form, token="other-token")},
    )
    assert resp.status_code == 403


async def test_valid_signature_reaches_the_handler(client: AsyncClient, enforced: None) -> None:
    """A correctly signed request runs the handler, which hangs up on no session."""
    form = {"CallSid": "CAsig0004"}
    resp = await client.post(
        VOICE_APP,
        data=form,
        headers={"X-Twilio-Signature": _signature(VOICE_APP, form)},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text


async def test_valid_signature_over_a_query_string_reaches_the_handler(
    client: AsyncClient, enforced: None
) -> None:
    """The reconstructed URL keeps the query string, so a signed one validates."""
    query = f"session_id={uuid.uuid4()}"
    form = {"CallSid": "CAsig0005"}

    resp = await client.post(
        f"{VOICE_APP}?{query}",
        data=form,
        headers={"X-Twilio-Signature": _signature(VOICE_APP, form, query=query)},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text


async def test_signature_computed_without_the_query_is_rejected(
    client: AsyncClient, enforced: None
) -> None:
    """Signing only the path does not authorise a request that carries a query."""
    query = f"session_id={uuid.uuid4()}"
    form = {"CallSid": "CAsig0006"}

    resp = await client.post(
        f"{VOICE_APP}?{query}",
        data=form,
        headers={"X-Twilio-Signature": _signature(VOICE_APP, form)},
    )
    assert resp.status_code == 403


async def test_tampered_form_field_is_rejected(client: AsyncClient, enforced: None) -> None:
    signature = _signature(VOICE_APP, {"CallSid": "CAsig0007"})
    resp = await client.post(
        VOICE_APP,
        data={"CallSid": "CAsig0007-tampered"},
        headers={"X-Twilio-Signature": signature},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Development: skipped only when no auth token is configured
# ---------------------------------------------------------------------------


async def test_development_without_a_token_skips_validation(
    client: AsyncClient, enforced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")

    resp = await client.post(VOICE_APP, data={"CallSid": "CAsig0008"})
    assert resp.status_code == 200
    assert "<Hangup" in resp.text


async def test_development_with_a_token_still_rejects_a_bad_signature(
    client: AsyncClient, enforced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    resp = await client.post(
        VOICE_APP,
        data={"CallSid": "CAsig0009"},
        headers={"X-Twilio-Signature": "wrong"},
    )
    assert resp.status_code == 403


async def test_development_with_a_token_accepts_a_good_signature(
    client: AsyncClient, enforced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    form = {"CallSid": "CAsig0010"}
    resp = await client.post(
        VOICE_APP,
        data=form,
        headers={"X-Twilio-Signature": _signature(VOICE_APP, form)},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text
