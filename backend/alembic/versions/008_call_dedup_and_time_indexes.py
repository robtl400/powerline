"""call dial-sid uniqueness and time-range query indexes

Revision ID: 008
Revises: 007
Create Date: 2026-09-10

Gives the call-complete idempotency check a database guarantee, and adds the
time-range indexes the session history, insights backfill and rep-lookup
cleanup queries scan. Every index here is built or dropped CONCURRENTLY, so no
ACCESS EXCLUSIVE lock is held; a build cancelled part-way leaves an INVALID
index that the next run clears before rebuilding.

Legs recorded under the session's parent CallSid predate the per-leg
`<parent>:<index>` naming, so they are renamed into that form rather than
deleted. Only rows that still share a (session_id, twilio_call_sid) pair after
the rename are true callback retries, and all but the earliest of those go.

`ix_call_sessions_campaign_id` from revision 006 is redundant once
`ix_call_sessions_campaign_created` exists, so it is dropped here.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Pre-`<parent>:<index>` legs carry the session's own CallSid. Numbering them
# in creation order reproduces the leg index the webhook now writes.
RENAME_PARENT_SID_LEGS = """
    WITH parent_legs AS (
        SELECT
            calls.id AS call_id,
            calls.twilio_call_sid AS parent_sid,
            row_number() OVER (
                PARTITION BY calls.session_id
                ORDER BY calls.created_at, calls.id
            ) - 1 AS leg_index
        FROM calls
        JOIN call_sessions s
          ON s.id = calls.session_id
         AND s.twilio_call_sid = calls.twilio_call_sid
        WHERE calls.twilio_call_sid <> ''
    )
    UPDATE calls
    SET twilio_call_sid = parent_legs.parent_sid || ':' || parent_legs.leg_index
    FROM parent_legs
    WHERE calls.id = parent_legs.call_id
"""

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
          AND (session_id, twilio_call_sid) IN (
              SELECT session_id, twilio_call_sid
              FROM calls
              WHERE twilio_call_sid <> ''
              GROUP BY 1, 2
              HAVING count(*) > 1
          )
    ) ranked
    WHERE calls.id = ranked.id
      AND ranked.rn > 1
"""

INSIGHTS_CANDIDATES_WHERE = "status = 'completed' AND quality_details IS NULL"
REP_LOOKUP_WHERE = "external_id = 'rep_lookup'"

INVALID_INDEX = """
    SELECT 1
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    WHERE c.relname = :name
      AND NOT i.indisvalid
"""


def drop_invalid_index(name: str) -> None:
    """Clear the stub a cancelled CONCURRENTLY build leaves behind."""
    leftover = op.get_bind().execute(sa.text(INVALID_INDEX), {"name": name}).scalar()
    if leftover:
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')


def upgrade() -> None:
    op.execute(RENAME_PARENT_SID_LEGS)
    op.execute(DEDUPE_CALLS)

    with op.get_context().autocommit_block():
        drop_invalid_index("ux_calls_session_dial_sid")
        op.create_index(
            "ux_calls_session_dial_sid",
            "calls",
            ["session_id", "twilio_call_sid"],
            unique=True,
            postgresql_where=sa.text("twilio_call_sid <> ''"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        drop_invalid_index("ix_call_sessions_created_at")
        op.create_index(
            "ix_call_sessions_created_at",
            "call_sessions",
            ["created_at"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        drop_invalid_index("ix_call_sessions_campaign_created")
        op.create_index(
            "ix_call_sessions_campaign_created",
            "call_sessions",
            ["campaign_id", "created_at"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        drop_invalid_index("ix_calls_insights_candidates")
        op.create_index(
            "ix_calls_insights_candidates",
            "calls",
            ["created_at"],
            postgresql_where=sa.text(INSIGHTS_CANDIDATES_WHERE),
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        drop_invalid_index("ix_targets_rep_lookup")
        op.create_index(
            "ix_targets_rep_lookup",
            "targets",
            ["created_at"],
            postgresql_where=sa.text(REP_LOOKUP_WHERE),
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.drop_index(
            "ix_call_sessions_campaign_id",
            table_name="call_sessions",
            postgresql_concurrently=True,
            if_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        drop_invalid_index("ix_call_sessions_campaign_id")
        op.create_index(
            "ix_call_sessions_campaign_id",
            "call_sessions",
            ["campaign_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.drop_index(
            "ix_targets_rep_lookup",
            table_name="targets",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_calls_insights_candidates",
            table_name="calls",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_call_sessions_campaign_created",
            table_name="call_sessions",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_call_sessions_created_at",
            table_name="call_sessions",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ux_calls_session_dial_sid",
            table_name="calls",
            postgresql_concurrently=True,
            if_exists=True,
        )
