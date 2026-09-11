"""audio slot integrity, foreign-key indexes, name/email uniqueness

Revision ID: 007
Revises: 006
Create Date: 2026-09-10

Dedupes audio_recordings before the slot uniqueness rules are enforced, so
pre-existing rows cannot abort the migration.

Lock notes for operators: the audio_recordings unique constraint, the
ux_audio_recordings_active partial unique index, and the campaigns/users/
phone_numbers constraint swaps all take ACCESS EXCLUSIVE on their table for
the duration of a full table scan. Run this migration in a maintenance window
sized for the audio_recordings and campaigns row counts. The plain lookup
indexes are built CONCURRENTLY and do not block writes.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Rows that collide on (campaign_id, key, version) keep the newest row's version
# and push the older ones past the slot's current high-water mark.
DEDUPE_VERSIONS = """
    WITH ranked AS (
        SELECT
            id,
            campaign_id,
            key,
            row_number() OVER (
                PARTITION BY campaign_id, key, version
                ORDER BY created_at DESC, id DESC
            ) AS rn
        FROM audio_recordings
    ),
    high_water AS (
        SELECT campaign_id, key, max(version) AS max_version
        FROM audio_recordings
        GROUP BY campaign_id, key
    ),
    renumbered AS (
        SELECT
            ranked.id,
            high_water.max_version + row_number() OVER (
                PARTITION BY ranked.campaign_id, ranked.key
                ORDER BY ranked.id
            ) AS new_version
        FROM ranked
        JOIN high_water
          ON high_water.campaign_id IS NOT DISTINCT FROM ranked.campaign_id
         AND high_water.key = ranked.key
        WHERE ranked.rn > 1
          AND ranked.campaign_id IS NOT NULL
    )
    UPDATE audio_recordings
    SET version = renumbered.new_version
    FROM renumbered
    WHERE audio_recordings.id = renumbered.id
"""

DEDUPE_ACTIVE = """
    WITH ranked AS (
        SELECT
            id,
            row_number() OVER (
                PARTITION BY campaign_id, key
                ORDER BY created_at DESC, id DESC
            ) AS rn
        FROM audio_recordings
        WHERE is_active
          AND campaign_id IS NOT NULL
    )
    UPDATE audio_recordings
    SET is_active = false
    FROM ranked
    WHERE audio_recordings.id = ranked.id
      AND ranked.rn > 1
"""

# (index name, table, columns)
LOOKUP_INDEXES = (
    ("ix_calls_session_id", "calls", ["session_id"]),
    ("ix_calls_target_id", "calls", ["target_id"]),
    ("ix_calls_campaign_id", "calls", ["campaign_id"]),
    ("ix_campaign_targets_target_id", "campaign_targets", ["target_id"]),
    (
        "ix_campaign_phone_numbers_phone_number_id",
        "campaign_phone_numbers",
        ["phone_number_id"],
    ),
)


def upgrade() -> None:
    op.execute(DEDUPE_VERSIONS)
    op.execute(DEDUPE_ACTIVE)

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

    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.drop_constraint("phone_numbers_number_key", "phone_numbers", type_="unique")
    op.drop_index("ix_phone_numbers_number", table_name="phone_numbers")
    op.create_index(
        "ix_phone_numbers_number", "phone_numbers", ["number"], unique=True
    )

    op.drop_constraint("campaigns_name_key", "campaigns", type_="unique")
    op.create_index(
        "ux_campaigns_name_active",
        "campaigns",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status <> 'archived'"),
    )

    with op.get_context().autocommit_block():
        for name, table, columns in LOOKUP_INDEXES:
            op.create_index(
                name, table, columns, postgresql_concurrently=True
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, _columns in reversed(LOOKUP_INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True)

    collisions = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT name FROM campaigns GROUP BY name "
                "HAVING count(*) > 1 ORDER BY name"
            )
        )
        .scalars()
        .all()
    )
    if collisions:
        raise RuntimeError(
            "Cannot restore the campaigns_name_key unique constraint: these "
            "campaign names are used by more than one row — "
            f"{', '.join(repr(name) for name in collisions)}. Rename or delete "
            "the duplicates, then run the downgrade again."
        )
    op.drop_index("ux_campaigns_name_active", table_name="campaigns")
    op.create_unique_constraint("campaigns_name_key", "campaigns", ["name"])

    op.drop_index("ix_phone_numbers_number", table_name="phone_numbers")
    op.create_index("ix_phone_numbers_number", "phone_numbers", ["number"])
    op.create_unique_constraint(
        "phone_numbers_number_key", "phone_numbers", ["number"]
    )

    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"])
    op.create_unique_constraint("users_email_key", "users", ["email"])

    op.drop_index("ux_audio_recordings_active", table_name="audio_recordings")
    op.drop_constraint(
        "uq_audio_recordings_campaign_key_version",
        "audio_recordings",
        type_="unique",
    )
