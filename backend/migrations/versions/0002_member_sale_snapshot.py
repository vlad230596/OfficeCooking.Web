"""Snapshot each cook member permanent sale."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_member_sale_snapshot"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cook_members",
        sa.Column("permanent_sale_snapshot", sa.REAL(), nullable=True),
    )
    op.execute(
        "UPDATE cook_members AS member "
        "SET permanent_sale_snapshot = users.permanent_sale "
        "FROM users WHERE users.id = member.user_id"
    )
    op.alter_column("cook_members", "permanent_sale_snapshot", nullable=False)


def downgrade() -> None:
    op.drop_column("cook_members", "permanent_sale_snapshot")
