"""add users.sessions_valid_from and the 'skipped' call status

Adds a nullable users.sessions_valid_from TIMESTAMPTZ that records the moment a
user's sessions were last revoked, so the session floor survives the loss of the
Redis key that normally carries it, and appends 'skipped' to the call_status
enum.

ALTER TYPE ... ADD VALUE cannot run inside a transaction block on PostgreSQL
before 12 and cannot be used in the same transaction that references the new
value, so the enum change runs in an autocommit block.

The downgrade drops the column only. PostgreSQL has no ALTER TYPE ... DROP
VALUE, so 'skipped' stays in call_status; removing it would mean recreating the
type and rewriting every column that uses it. The leftover value is inert for
any code that never writes it.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("sessions_valid_from", sa.DateTime(timezone=True), nullable=True),
    )

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE call_status ADD VALUE IF NOT EXISTS 'skipped'")


def downgrade() -> None:
    op.drop_column("users", "sessions_valid_from")
