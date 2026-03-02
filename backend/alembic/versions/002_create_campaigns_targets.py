"""create campaigns and targets tables

Revision ID: 002
Revises: 001
Create Date: 2026-02-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types idempotently — safe to re-run if a previous attempt
    # partially succeeded and left stray types in the DB.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE campaign_status AS ENUM ('draft', 'paused', 'live', 'archived');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE campaign_type AS ENUM ('custom');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE target_ordering AS ENUM ('in_order', 'shuffle');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # targets table
    op.create_table(
        "targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
    )

    # campaigns table — use postgresql.ENUM(create_type=False) since the types
    # are already created above; sa.Enum does not support create_type=False.
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("draft", "paused", "live", "archived", name="campaign_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "campaign_type",
            postgresql.ENUM("custom", name="campaign_type", create_type=False),
            nullable=False,
            server_default="custom",
        ),
        sa.Column("language", sa.String(5), nullable=False, server_default="en-US"),
        sa.Column(
            "target_ordering",
            postgresql.ENUM("in_order", "shuffle", name="target_ordering", create_type=False),
            nullable=False,
            server_default="in_order",
        ),
        sa.Column("call_maximum", sa.Integer, nullable=True),
        sa.Column("allow_call_in", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("allow_webrtc", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("allow_phone_callback", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("lookup_validate", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("lookup_require_mobile", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("embed_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("talking_points", sa.Text, nullable=True),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_campaigns_name", "campaigns", ["name"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    # campaign_targets join table
    op.create_table(
        "campaign_targets",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("targets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("order", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("campaign_targets")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_name", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_table("targets")
    op.execute("DROP TYPE IF EXISTS campaign_status")
    op.execute("DROP TYPE IF EXISTS campaign_type")
    op.execute("DROP TYPE IF EXISTS target_ordering")
