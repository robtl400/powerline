"""campaign rate_limit default + call_sessions campaign_id index

Revision ID: 006
Revises: 005
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("campaigns", "rate_limit", server_default="5")
    op.execute("UPDATE campaigns SET rate_limit = 5 WHERE rate_limit IS NULL")
    # Supports the per-campaign call ceiling count on the public call paths.
    op.create_index("ix_call_sessions_campaign_id", "call_sessions", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_call_sessions_campaign_id", table_name="call_sessions")
    op.alter_column("campaigns", "rate_limit", server_default=None)
