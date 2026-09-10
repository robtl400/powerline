"""Shared telephony return types.

Define return dataclasses here (not in provider files) so callers can import
them alongside the provider without a circular import.
"""
from __future__ import annotations

import dataclasses


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
