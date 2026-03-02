"""Twilio implementation of the TelephonyProvider Protocol.

All methods are synchronous — the Twilio SDK does not support async.
Callers in async contexts must wrap calls with asyncio.get_running_loop().run_in_executor().
"""
from __future__ import annotations

import structlog
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.services.telephony.base import CallResult, LookupResult, PhoneNumberInfo

log = structlog.get_logger()


class TwilioProvider:
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        api_key_sid: str,
        api_key_secret: str,
        twiml_app_sid: str,
    ) -> None:
        self._client = Client(account_sid, auth_token)
        self._auth_token = auth_token
        self._api_key_sid = api_key_sid
        self._api_key_secret = api_key_secret
        self._twiml_app_sid = twiml_app_sid

    def create_call(self, to: str, from_: str, url: str, **kwargs) -> CallResult:
        call = self._client.calls.create(to=to, from_=from_, url=url, **kwargs)
        return CallResult(sid=call.sid, status=call.status)

    def generate_access_token(self, identity: str, grants: list) -> str:
        """Generate a JWT for browser/mobile WebRTC clients.

        Uses API Key credentials (SK...), NOT the main auth token.
        AccessToken TTL is 3600s — Twilio's recommended default for WebRTC sessions.
        """
        token = AccessToken(
            self._client.account_sid,
            self._api_key_sid,
            self._api_key_secret,
            identity=identity,
            ttl=3600,
        )
        for grant in grants:
            token.add_grant(grant)
        return token.to_jwt()

    def generate_voice_grant(self) -> VoiceGrant:
        """Convenience method to create a VoiceGrant for the configured TwiML App."""
        return VoiceGrant(outgoing_application_sid=self._twiml_app_sid)

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
