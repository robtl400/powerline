"""Telephony service package.

Exposes a module-level singleton TwilioProvider via get_provider().
The singleton avoids recreating the Twilio HTTP session pool on every request.
"""
from __future__ import annotations

from app.services.telephony.twilio_provider import TwilioProvider

_provider: TwilioProvider | None = None


def get_provider() -> TwilioProvider:
    global _provider
    if _provider is None:
        from app.config import settings

        _provider = TwilioProvider(
            account_sid=settings.TWILIO_ACCOUNT_SID,
            auth_token=settings.TWILIO_AUTH_TOKEN,
            api_key_sid=settings.TWILIO_API_KEY_SID,
            api_key_secret=settings.TWILIO_API_KEY_SECRET,
            twiml_app_sid=settings.TWILIO_TWIML_APP_SID,
        )
    return _provider


__all__ = ["TwilioProvider", "get_provider"]
