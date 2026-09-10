"""audio slot integrity, foreign-key indexes, name/email uniqueness

Revision ID: 007
Revises: 006
Create Date: 2026-09-10

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_audio_recordings_campaign_key_version",
        "audio_recordings",
        ["campaign_id", "key", "version"],
    )
    op.create_index(
        "ux_audio_recordings_active",
        "audio_recordings",
        ["campaign_id", "key"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_index("ix_calls_session_id", "calls", ["session_id"])
    op.create_index("ix_calls_target_id", "calls", ["target_id"])
    op.create_index("ix_calls_campaign_id", "calls", ["campaign_id"])
    op.create_index("ix_campaign_targets_target_id", "campaign_targets", ["target_id"])
    op.create_index(
        "ix_campaign_phone_numbers_phone_number_id",
        "campaign_phone_numbers",
        ["phone_number_id"],
    )

    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.drop_constraint("campaigns_name_key", "campaigns", type_="unique")
    op.create_index(
        "ux_campaigns_name_active",
        "campaigns",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status <> 'archived'"),
    )


def downgrade() -> None:
    op.drop_index("ux_campaigns_name_active", table_name="campaigns")
    op.create_unique_constraint("campaigns_name_key", "campaigns", ["name"])

    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"])

    op.drop_index(
        "ix_campaign_phone_numbers_phone_number_id",
        table_name="campaign_phone_numbers",
    )
    op.drop_index("ix_campaign_targets_target_id", table_name="campaign_targets")
    op.drop_index("ix_calls_campaign_id", table_name="calls")
    op.drop_index("ix_calls_target_id", table_name="calls")
    op.drop_index("ix_calls_session_id", table_name="calls")

    op.drop_index("ux_audio_recordings_active", table_name="audio_recordings")
    op.drop_constraint(
        "uq_audio_recordings_campaign_key_version",
        "audio_recordings",
        type_="unique",
    )
