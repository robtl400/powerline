import asyncio

import structlog
from twilio.rest import Client

from app.config import settings
from app.services.digest import fingerprint

log = structlog.get_logger()


def send_sms(to: str, body: str) -> str:
    """Send an SMS via Twilio. Returns the message SID.

    The Twilio client is synchronous and performs blocking network I/O, so
    async callers must go through send_sms_async.
    """
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        to=to,
        from_=settings.TWILIO_FROM_NUMBER,
        body=body,
    )
    log.info("sms_sent", to_fingerprint=fingerprint(to), sid=message.sid)
    return message.sid


async def send_sms_async(to: str, body: str) -> str:
    """Run the blocking Twilio client off the event loop."""
    return await asyncio.get_running_loop().run_in_executor(None, send_sms, to, body)
