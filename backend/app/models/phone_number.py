import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    twilio_sid: Mapped[str] = mapped_column(String(34), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(
        Enum("twilio", name="phone_number_provider"),
        nullable=False,
        default="twilio",
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Plain string, not an Enum — Twilio's trust status strings can change as their
    # Trust Hub product evolves (e.g. "twilio-approved", "pending-review", "in-review").
    trust_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )
    trust_product_sid: Mapped[str | None] = mapped_column(String(34), nullable=True)
