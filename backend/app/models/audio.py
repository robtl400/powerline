import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Valid audio slot keys — enforced at the Pydantic schema layer, not in the DB.
# Using a String column keeps the schema stable if slot names evolve.
AUDIO_KEYS = frozenset({
    "msg_intro",
    "msg_intro_confirm",
    "msg_target_intro",
    "msg_call_block_intro",
    "msg_between_calls",
    "msg_target_busy",
    "msg_goodbye",
})


class AudioRecording(Base):
    __tablename__ = "audio_recordings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # Nullable so global/default recordings can live at campaign_id=NULL in the future.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tts_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # No unique constraint on (campaign_id, key) — multiple versions are allowed.
    # The activate endpoint enforces at most one is_active=True per (campaign_id, key).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    campaign = relationship("Campaign", foreign_keys=[campaign_id])
