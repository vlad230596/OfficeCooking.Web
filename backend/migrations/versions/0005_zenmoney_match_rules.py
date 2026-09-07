"""Remember manual ZenMoney sender matches.

Revision ID: 0005_zenmoney_match_rules
Revises: 0004_zenmoney_import
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_zenmoney_match_rules"
down_revision: str | Sequence[str] | None = "0004_zenmoney_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "zenmoney_match_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("kind IN ('phone', 'name')", name="kind_allowed"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "pattern"),
    )


def downgrade() -> None:
    op.drop_table("zenmoney_match_rules")
