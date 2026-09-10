"""Twilio telephony provider.

All methods are synchronous — the Twilio SDK does not support async.
Callers in async contexts must wrap calls with asyncio.get_running_loop().run_in_executor().
"""
from __future__ import annotations

import structlog
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.services.telephony.base import CallResult, LookupResult, PhoneNumberInfo

log = structlog.get_logger()


class TwilioProvider:
    def __init__(self, account_sid: str, auth_token: str) -> None:
        self._client = Client(account_sid, auth_token)
        self._auth_token = auth_token

    def create_call(self, to: str, from_: str, url: str, **kwargs) -> CallResult:
        call = self._client.calls.create(to=to, from_=from_, url=url, **kwargs)
        return CallResult(sid=call.sid, status=call.status)

    def list_phone_numbers(self) -> list[PhoneNumberInfo]:
        numbers = self._client.incoming_phone_numbers.list()
        return [
            PhoneNumberInfo(
                sid=n.sid,
                number=n.phone_number,
                label=n.friendly_name,
                capabilities={
                    "voice": n.capabilities.get("voice", False),
                    "sms": n.capabilities.get("sms", False),
                    "mms": n.capabilities.get("mms", False),
                },
                trust_status="unknown",
            )
            for n in numbers
        ]

    def validate_phone(self, number: str) -> LookupResult:
        """Validate a phone number via Twilio Lookup v2.

        line_type_intelligence is a paid add-on — guard the response with `or {}`
        since the field may be None if the feature isn't provisioned.
        """
        result = self._client.lookups.v2.phone_numbers(number).fetch(
            fields="line_type_intelligence"
        )
        lti = result.line_type_intelligence or {}
        return LookupResult(
            phone=result.phone_number,
            is_valid=result.valid,
            line_type=lti.get("type"),
            raw={"line_type_intelligence": lti},
        )

    def validate_request(self, url: str, post_vars: dict, signature: str) -> bool:
        """Validate that a webhook request originated from Twilio."""
        validator = RequestValidator(self._auth_token)
        return validator.validate(url, post_vars, signature)
