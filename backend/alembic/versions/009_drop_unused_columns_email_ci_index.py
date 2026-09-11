"""drop unused call-session and campaign columns, add case-insensitive email index

Revision ID: 009
Revises: 008
Create Date: 2026-09-10

Adds a unique index on lower(users.email) so two accounts cannot differ only by
the case of their address, then drops call_sessions.from_number and
campaigns.allow_call_in, neither of which any query reads. The index is built
CONCURRENTLY in an autocommit block, so no ACCESS EXCLUSIVE lock is held; the
column drops are ordinary transactional statements that take a brief ACCESS
EXCLUSIVE lock each.

DESTRUCTIVE: the two column drops discard their data and the downgrade restores
only empty columns. Take a database backup before applying this revision.

The index is built before the drops, so a migration that aborts on colliding
addresses still has both columns. The pre-check names the colliding addresses
so an operator can merge the accounts first.
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
    collisions = op.get_bind().execute(sa.text(CASE_VARIANT_EMAILS)).all()
    if collisions:
        listed = ", ".join(f"{row.normalized} ({row.accounts} accounts)" for row in collisions)
        raise RuntimeError(
            "users.email holds addresses that differ only by case: "
            f"{listed}. Merge them before applying revision 009."
        )

    with op.get_context().autocommit_block():
        drop_invalid_index("ix_users_email_lower")
        op.create_index(
            "ix_users_email_lower",
            "users",
            [sa.text("lower(email)")],
            unique=True,
            postgresql_concurrently=True,
            if_not_exists=True,
        )

    op.drop_column("call_sessions", "from_number")
    op.drop_column("campaigns", "allow_call_in")


def downgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("allow_call_in", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column("call_sessions", sa.Column("from_number", sa.String(20), nullable=True))

    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_users_email_lower",
            table_name="users",
            postgresql_concurrently=True,
            if_exists=True,
        )
