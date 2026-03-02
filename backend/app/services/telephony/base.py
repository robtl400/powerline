"""Abstract telephony provider interface and shared return types.

Define return dataclasses here (not in provider files) to prevent circular
imports when the lookup service or TwiML builder imports them alongside
the provider Protocol.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Protocol, runtime_checkable


@dataclasses.dataclass
class CallResult:
    sid: str
    status: str


@dataclasses.dataclass
class PhoneNumberInfo:
    sid: str            # e.g. "PNxxx..."
    number: str         # E.164
    label: str          # friendly_name from Twilio
    capabilities: dict  # {"voice": True, "sms": True, "mms": False}
    trust_status: str   # "unknown" default; populated by Trust Hub in future


@dataclasses.dataclass
class LookupResult:
    phone: str
    is_valid: bool
    line_type: str | None   # "mobile", "landline", "voip", "nonFixedVoip", "tollFree", or None
    raw: dict               # full API response for future use


@runtime_checkable
class TelephonyProvider(Protocol):
    def create_call(self, to: str, from_: str, url: str, **kwargs: Any) -> CallResult: ...

    def generate_access_token(self, identity: str, grants: list[Any]) -> str: ...

    def list_phone_numbers(self) -> list[PhoneNumberInfo]: ...

    def validate_phone(self, number: str) -> LookupResult: ...

    def validate_request(self, url: str, post_vars: dict, signature: str) -> bool: ...
