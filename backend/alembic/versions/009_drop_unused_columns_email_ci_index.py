"""drop unused call-session and campaign columns, add case-insensitive email index

Revision ID: 009
Revises: 008
Create Date: 2026-09-10

Drops call_sessions.from_number and campaigns.allow_call_in, neither of which
any query reads, and adds a unique index on lower(users.email) so two accounts
cannot differ only by the case of their address. The index is built
CONCURRENTLY in an autocommit block, so no ACCESS EXCLUSIVE lock is held; the
column drops are ordinary transactional statements that take a brief ACCESS
EXCLUSIVE lock each.

The index build aborts the migration if any addresses already collide
case-insensitively; the raised error names them so an operator can merge the
accounts first.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CASE_VARIANT_EMAILS = """
    SELECT lower(email) AS normalized, count(*) AS accounts
    FROM users
    GROUP BY lower(email)
    HAVING count(*) > 1
    ORDER BY normalized
"""


def upgrade() -> None:
    collisions = op.get_bind().execute(sa.text(CASE_VARIANT_EMAILS)).all()
    if collisions:
        listed = ", ".join(f"{row.normalized} ({row.accounts} accounts)" for row in collisions)
        raise RuntimeError(
            "users.email holds addresses that differ only by case: "
            f"{listed}. Merge them before applying revision 009."
        )

    op.drop_column("call_sessions", "from_number")
    op.drop_column("campaigns", "allow_call_in")

    with op.get_context().autocommit_block():
        op.create_index(
            "ix_users_email_lower",
            "users",
            [sa.text("lower(email)")],
            unique=True,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_users_email_lower",
            table_name="users",
            postgresql_concurrently=True,
        )

    op.add_column(
        "campaigns",
        sa.Column("allow_call_in", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column("call_sessions", sa.Column("from_number", sa.String(20), nullable=True))
