import structlog
from twilio.rest import Client

from app.config import settings

log = structlog.get_logger()


def send_sms(to: str, body: str) -> str:
    """Send an SMS via Twilio. Returns the message SID."""
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        to=to,
        from_=settings.TWILIO_FROM_NUMBER,
        body=body,
    )
    log.info("sms_sent", to=to, sid=message.sid)
    return message.sid
