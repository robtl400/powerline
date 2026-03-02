import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="RESTRICT"),
        nullable=False,
    )
    caller_phone_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caller_location: Mapped[str | None] = mapped_column(String(20), nullable=True)
    connection_type: Mapped[str] = mapped_column(
        Enum("webrtc", "outbound_phone", "inbound_phone", name="connection_type"),
        nullable=False,
    )
    from_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Populated on first voice-app webhook hit; empty string until then.
    twilio_call_sid: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(
        Enum("initiated", "in_progress", "completed", "failed", name="call_session_status"),
        nullable=False,
        default="initiated",
    )
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referral_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    browser_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    campaign = relationship("Campaign", foreign_keys=[campaign_id])
    calls = relationship("Call", back_populates="session", cascade="all, delete-orphan")
