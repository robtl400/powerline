import hashlib

import structlog
from twilio.rest import Client

from app.config import settings

log = structlog.get_logger()


def phone_fingerprint(number: str) -> str:
    """Truncated hash of a phone number, safe to correlate on in logs."""
    return hashlib.sha256(number.encode()).hexdigest()[:12]


def send_sms(to: str, body: str) -> str:
    """Send an SMS via Twilio. Returns the message SID.

    The Twilio client is synchronous and performs blocking network I/O, so
    async callers must dispatch this through a thread (run_in_executor).
    """
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        to=to,
        from_=settings.TWILIO_FROM_NUMBER,
        body=body,
    )
    log.info("sms_sent", to_fingerprint=phone_fingerprint(to), sid=message.sid)
    return message.sid
