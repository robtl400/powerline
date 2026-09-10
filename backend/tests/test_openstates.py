"""Tests for the OpenStates v3 provider.

A v3 Person has no contact_details block — phone numbers live on the offices
list, so these tests pin the office parsing against realistic payloads.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import settings
from app.services.civic import openstates
from app.services.civic.google_civic import MissingApiKeyError


def _person(name: str, offices: list[dict] | None, title: str = "Senator") -> dict:
    person = {
        "id": f"ocd-person/{name}",
        "name": name,
        "current_role": {"title": title, "org_classification": "upper"},
    }
    if offices is not None:
        person["offices"] = offices
    return person


def _mock_response(people: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"results": people},
        request=httpx.Request("GET", "https://v3.openstates.org/api/v3/people.geo"),
    )


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENSTATES_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def known_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(openstates._CENTROIDS, "90210", (34.0901, -118.4065))


async def test_office_voice_is_used_and_officeless_people_skipped() -> None:
    people = [
        _person(
            "Sen. Capitol",
            [
                {
                    "name": "District Office",
                    "classification": "district",
                    "address": "1 Main St",
                    "voice": "916-555-0142",
                },
                {
                    "name": "Capitol Office",
                    "classification": "capitol",
                    "address": "1315 10th St",
                    "voice": "916-555-0100",
                    "fax": "916-555-0101",
                },
            ],
        ),
        _person("Rep. Silent", [{"name": "Capitol Office", "classification": "capitol"}]),
        _person("Rep. Officeless", None, title="Representative"),
        _person("Rep. Empty", []),
    ]

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get:
        get.return_value = _mock_response(people)
        reps = await openstates.fetch_state_reps("90210")

    assert [r.name for r in reps] == ["Sen. Capitol"]
    assert reps[0].phone == "916-555-0100"
    assert reps[0].level == "state"
    assert reps[0].title == "Senator, upper"


async def test_district_office_used_when_no_capitol_number() -> None:
    people = [
        _person(
            "Sen. District",
            [
                {"name": "Capitol Office", "classification": "capitol", "voice": ""},
                {"name": "District Office", "classification": "district", "voice": "503-555-0188"},
            ],
        ),
    ]

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get:
        get.return_value = _mock_response(people)
        reps = await openstates.fetch_state_reps("90210")

    assert [r.phone for r in reps] == ["503-555-0188"]


async def test_unclassified_office_is_last_resort() -> None:
    people = [
        _person(
            "Sen. Other",
            [
                {"name": "Mailing Address", "classification": "", "voice": "212-555-0170"},
            ],
        ),
    ]

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get:
        get.return_value = _mock_response(people)
        reps = await openstates.fetch_state_reps("90210")

    assert [r.phone for r in reps] == ["212-555-0170"]


async def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENSTATES_API_KEY", "")
    with pytest.raises(MissingApiKeyError):
        await openstates.fetch_state_reps("90210")


async def test_unknown_zip_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(openstates._CENTROIDS, "00000", raising=False)
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get:
        assert await openstates.fetch_state_reps("00000") == []
    get.assert_not_called()
