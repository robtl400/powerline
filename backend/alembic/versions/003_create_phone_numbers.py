"""create phone_numbers and campaign_phone_numbers tables

Revision ID: 003
Revises: 002
Create Date: 2026-02-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the phone_number_provider enum idempotently.
    # Only "twilio" for now; additional providers added via future migrations.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE phone_number_provider AS ENUM ('twilio');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    op.create_table(
        "phone_numbers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("number", sa.String(20), nullable=False, unique=True),
        sa.Column("twilio_sid", sa.String(34), nullable=False, unique=True),
        sa.Column(
            "provider",
            postgresql.ENUM("twilio", name="phone_number_provider", create_type=False),
            nullable=False,
            server_default="twilio",
        ),
        sa.Column("label", sa.String(100), nullable=False, server_default=""),
        sa.Column(
            "capabilities",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "trust_status",
            sa.String(20),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("trust_product_sid", sa.String(34), nullable=True),
    )
    op.create_index("ix_phone_numbers_number", "phone_numbers", ["number"])

    op.create_table(
        "campaign_phone_numbers",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "phone_number_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("phone_numbers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    # Drop FK-dependent table first, then the referenced table, then the type.
    op.drop_table("campaign_phone_numbers")
    op.drop_index("ix_phone_numbers_number", table_name="phone_numbers")
    op.drop_table("phone_numbers")
    op.execute("DROP TYPE IF EXISTS phone_number_provider")
