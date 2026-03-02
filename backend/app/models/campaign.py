import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "paused", "live", "archived", name="campaign_status"),
        nullable=False,
        default="draft",
    )
    campaign_type: Mapped[str] = mapped_column(
        Enum("custom", name="campaign_type"),
        nullable=False,
        default="custom",
    )
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en-US")
    target_ordering: Mapped[str] = mapped_column(
        Enum("in_order", "shuffle", name="target_ordering"),
        nullable=False,
        default="in_order",
    )
    call_maximum: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_call_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_webrtc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_phone_callback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lookup_validate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lookup_require_mobile: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    embed_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    talking_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by = relationship("User", foreign_keys=[created_by_id])
    campaign_targets = relationship(
        "CampaignTarget",
        cascade="all, delete-orphan",
        order_by="CampaignTarget.order",
    )
