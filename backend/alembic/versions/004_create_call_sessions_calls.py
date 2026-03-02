"""create call_sessions and calls tables

Revision ID: 004
Revises: 003
Create Date: 2026-02-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums idempotently — safe to re-run if partially applied.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE connection_type AS ENUM ('webrtc', 'outbound_phone', 'inbound_phone');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE call_session_status AS ENUM ('initiated', 'in_progress', 'completed', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE call_status AS ENUM (
                'queued', 'ringing', 'in_progress', 'completed',
                'busy', 'no_answer', 'failed', 'canceled'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    op.create_table(
        "call_sessions",
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
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("caller_phone_hash", sa.String(64), nullable=True),
        sa.Column("caller_location", sa.String(20), nullable=True),
        sa.Column(
            "connection_type",
            postgresql.ENUM("webrtc", "outbound_phone", "inbound_phone", name="connection_type", create_type=False),
            nullable=False,
        ),
        sa.Column("from_number", sa.String(20), nullable=True),
        sa.Column("twilio_call_sid", sa.String(40), nullable=False, server_default=""),
        sa.Column(
            "status",
            postgresql.ENUM("initiated", "in_progress", "completed", "failed", name="call_session_status", create_type=False),
            nullable=False,
            server_default="initiated",
        ),
        sa.Column("duration", sa.Integer, nullable=True),
        sa.Column("referral_code", sa.String(64), nullable=True),
        sa.Column("browser_info", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_call_sessions_twilio_call_sid", "call_sessions", ["twilio_call_sid"])

    op.create_table(
        "calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("targets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("twilio_call_sid", sa.String(40), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued", "ringing", "in_progress", "completed",
                "busy", "no_answer", "failed", "canceled",
                name="call_status",
                create_type=False,
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("duration", sa.Integer, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("quality_details", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_calls_twilio_call_sid", "calls", ["twilio_call_sid"])


def downgrade() -> None:
    op.drop_index("ix_calls_twilio_call_sid", table_name="calls")
    op.drop_table("calls")
    op.drop_index("ix_call_sessions_twilio_call_sid", table_name="call_sessions")
    op.drop_table("call_sessions")
    op.execute("DROP TYPE IF EXISTS call_status")
    op.execute("DROP TYPE IF EXISTS call_session_status")
    op.execute("DROP TYPE IF EXISTS connection_type")
