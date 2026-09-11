"""X-Forwarded-For handling in get_client_ip.

Every case pins settings.TRUSTED_PROXIES to a distinct string: the parsed
networks are cached on that raw string, so a fresh value is a fresh parse.
"""
from __future__ import annotations

import pytest
from starlette.requests import Request

import app.dependencies as dependencies
from app.config import settings
from app.dependencies import get_client_ip


@pytest.fixture
def trusted(monkeypatch: pytest.MonkeyPatch):
    """Set TRUSTED_PROXIES for one test, with a cleared parse cache."""

    def install(raw: str) -> None:
        monkeypatch.setattr(dependencies, "_trusted_proxy_cache", None)
        monkeypatch.setattr(settings, "TRUSTED_PROXIES", raw)

    return install


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/health",
            "headers": headers,
            "client": (peer, 40000),
        }
    )


def test_untrusted_peer_ignores_forwarded_header(trusted) -> None:
    trusted("10.1.0.0/16")
    request = _request("203.0.113.9", "198.51.100.4")
    assert get_client_ip(request) == "203.0.113.9"


def test_no_trusted_proxies_configured_ignores_forwarded_header(trusted) -> None:
    trusted("")
    request = _request("10.2.0.5", "198.51.100.4")
    assert get_client_ip(request) == "10.2.0.5"


def test_trusted_peer_takes_the_rightmost_non_proxy_hop(trusted) -> None:
    trusted("10.3.0.0/16")
    request = _request("10.3.0.5", "198.51.100.4, 203.0.113.9, 10.3.0.6")
    assert get_client_ip(request) == "203.0.113.9"


def test_trusted_peer_without_forwarded_header_uses_the_peer(trusted) -> None:
    trusted("10.4.0.0/16")
    assert get_client_ip(_request("10.4.0.5")) == "10.4.0.5"


def test_fully_trusted_chain_falls_back_to_the_peer(trusted) -> None:
    trusted("10.5.0.0/16")
    request = _request("10.5.0.5", "10.5.0.6, 10.5.0.7")
    assert get_client_ip(request) == "10.5.0.5"


def test_garbage_forwarded_entry_is_skipped(trusted) -> None:
    trusted("10.6.0.0/16")
    request = _request("10.6.0.5", "203.0.113.9, not-an-ip")
    assert get_client_ip(request) == "203.0.113.9"


def test_forwarded_chain_of_only_garbage_falls_back_to_the_peer(trusted) -> None:
    trusted("10.7.0.0/16")
    request = _request("10.7.0.5", "not-an-ip, , <script>")
    assert get_client_ip(request) == "10.7.0.5"


def test_invalid_trusted_proxy_entry_is_ignored_with_a_warning(trusted, monkeypatch) -> None:
    warnings: list[tuple[str, dict]] = []

    class _Recorder:
        def warning(self, event: str, **kw) -> None:
            warnings.append((event, kw))

    monkeypatch.setattr(dependencies, "log", _Recorder())
    trusted("10.8.0.0/16, 300.300.300.300/99")

    request = _request("10.8.0.5", "203.0.113.9")
    assert get_client_ip(request) == "203.0.113.9"
    assert ("trusted_proxy_invalid", {"entry": "300.300.300.300/99"}) in warnings


def test_missing_client_returns_an_empty_peer(trusted) -> None:
    trusted("10.9.0.0/16")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/health",
            "headers": [(b"x-forwarded-for", b"203.0.113.9")],
            "client": None,
        }
    )
    assert get_client_ip(request) == ""
