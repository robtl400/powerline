import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("call_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Nullable FKs so Call records survive campaign/target deletion.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("targets.id", ondelete="SET NULL"),
        nullable=True,
    )
    twilio_call_sid: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        Enum(
            "queued",
            "ringing",
            "in_progress",
            "completed",
            "busy",
            "no_answer",
            "failed",
            "canceled",
            name="call_status",
        ),
        nullable=False,
        default="queued",
    )
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Populated by Session 10 Voice Insights task.
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    session = relationship("CallSession", back_populates="calls")
    campaign = relationship("Campaign", foreign_keys=[campaign_id])
    target = relationship("Target", foreign_keys=[target_id])
