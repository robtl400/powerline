"""add audio_recordings, blocklist, campaign.rate_limit

Revision ID: 005
Revises: 004
Create Date: 2026-02-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No new PG enums — audio key is a plain String column.

    op.create_table(
        "audio_recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("tts_text", sa.Text, nullable=True),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default="false"
        ),
    )
    op.create_index(
        "ix_audio_recordings_campaign_id", "audio_recordings", ["campaign_id"]
    )
    # Composite index for the hottest query: find active record for (campaign, key).
    op.create_index(
        "ix_audio_recordings_campaign_key_active",
        "audio_recordings",
        ["campaign_id", "key", "is_active"],
    )

    op.create_table(
        "blocklist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("phone_hash", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_blocklist_phone_hash", "blocklist", ["phone_hash"])
    op.create_index("ix_blocklist_ip_address", "blocklist", ["ip_address"])

    op.add_column(
        "campaigns",
        sa.Column("rate_limit", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "rate_limit")
    op.drop_index("ix_blocklist_ip_address", table_name="blocklist")
    op.drop_index("ix_blocklist_phone_hash", table_name="blocklist")
    op.drop_table("blocklist")
    op.drop_index(
        "ix_audio_recordings_campaign_key_active", table_name="audio_recordings"
    )
    op.drop_index(
        "ix_audio_recordings_campaign_id", table_name="audio_recordings"
    )
    op.drop_table("audio_recordings")
