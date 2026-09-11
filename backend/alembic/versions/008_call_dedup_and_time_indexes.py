"""call dial-sid uniqueness and time-range query indexes

Revision ID: 008
Revises: 007
Create Date: 2026-09-10

Gives the call-complete idempotency check a database guarantee, and adds the
time-range indexes the session history, insights backfill and rep-lookup
cleanup queries scan. Every index here is built CONCURRENTLY, so no ACCESS
EXCLUSIVE lock is held; the dedupe DELETE that precedes them is an ordinary
transactional statement.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Twilio can retry a status callback; the earliest row per dial is the one the
# rest of the schema already references.
DEDUPE_CALLS = """
    DELETE FROM calls
    USING (
        SELECT
            id,
            row_number() OVER (
                PARTITION BY session_id, twilio_call_sid
                ORDER BY created_at ASC, id ASC
            ) AS rn
        FROM calls
        WHERE twilio_call_sid <> ''
    ) ranked
    WHERE calls.id = ranked.id
      AND ranked.rn > 1
"""

INSIGHTS_CANDIDATES_WHERE = "status = 'completed' AND quality_details IS NULL"
REP_LOOKUP_WHERE = "external_id = 'rep_lookup'"


def upgrade() -> None:
    op.execute(DEDUPE_CALLS)

    with op.get_context().autocommit_block():
        op.create_index(
            "ux_calls_session_dial_sid",
            "calls",
            ["session_id", "twilio_call_sid"],
            unique=True,
            postgresql_where=sa.text("twilio_call_sid <> ''"),
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_call_sessions_created_at",
            "call_sessions",
            ["created_at"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_call_sessions_campaign_created",
            "call_sessions",
            ["campaign_id", "created_at"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_calls_insights_candidates",
            "calls",
            ["created_at"],
            postgresql_where=sa.text(INSIGHTS_CANDIDATES_WHERE),
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_targets_rep_lookup",
            "targets",
            ["created_at"],
            postgresql_where=sa.text(REP_LOOKUP_WHERE),
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_targets_rep_lookup",
            table_name="targets",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_calls_insights_candidates",
            table_name="calls",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_call_sessions_campaign_created",
            table_name="call_sessions",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_call_sessions_created_at",
            table_name="call_sessions",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ux_calls_session_dial_sid",
            table_name="calls",
            postgresql_concurrently=True,
        )
