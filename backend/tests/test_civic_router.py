"""Fan-out and failure handling in the civic LevelRouter."""
from __future__ import annotations

import pytest

import app.services.civic.router as router_module
from app.services.civic.base import RepInfo
from app.services.civic.google_civic import MissingApiKeyError
from app.services.civic.router import LevelRouter

ZIP = "94110"

FEDERAL = RepInfo(name="Fed Rep", title="Senator", phone="+15550000001", level="federal")
STATE = RepInfo(name="State Rep", title="Assemblymember", phone="+15550000002", level="state")


def _returns(*reps: RepInfo):
    async def provider(zip_code: str) -> list[RepInfo]:
        assert zip_code == ZIP
        return list(reps)

    return provider


def _raises(exc: BaseException):
    async def provider(zip_code: str) -> list[RepInfo]:
        raise exc

    return provider


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch):
    """Replace the real provider map for one test."""

    def install(**mapping):
        monkeypatch.setattr(router_module, "_PROVIDER_MAP", dict(mapping))

    return install


async def test_a_failing_provider_still_returns_the_other_levels(providers) -> None:
    providers(federal=_raises(RuntimeError("upstream down")), state=_returns(STATE))

    result = await LevelRouter().lookup(ZIP, {"target_levels": ["federal", "state"]})

    assert result == [STATE]


async def test_both_providers_contribute(providers) -> None:
    providers(federal=_returns(FEDERAL), state=_returns(STATE))

    result = await LevelRouter().lookup(ZIP, {"target_levels": ["federal", "state"]})

    assert sorted(r.level for r in result) == ["federal", "state"]


async def test_missing_api_key_propagates(providers) -> None:
    providers(federal=_raises(MissingApiKeyError("GOOGLE_CIVIC_API_KEY")), state=_returns(STATE))

    with pytest.raises(MissingApiKeyError):
        await LevelRouter().lookup(ZIP, {"target_levels": ["federal", "state"]})


async def test_unknown_level_yields_no_reps(providers) -> None:
    providers(federal=_returns(FEDERAL))

    assert await LevelRouter().lookup(ZIP, {"target_levels": ["martian"]}) == []


async def test_empty_levels_yield_no_reps(providers) -> None:
    providers(federal=_returns(FEDERAL))

    assert await LevelRouter().lookup(ZIP, {"target_levels": []}) == []


async def test_unknown_levels_are_dropped_but_known_ones_run(providers) -> None:
    providers(federal=_returns(FEDERAL))

    result = await LevelRouter().lookup(ZIP, {"target_levels": ["martian", "federal"]})

    assert result == [FEDERAL]


async def test_default_level_is_federal(providers) -> None:
    providers(federal=_returns(FEDERAL), state=_returns(STATE))

    assert await LevelRouter().lookup(ZIP, {}) == [FEDERAL]
