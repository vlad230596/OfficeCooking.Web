"""Scope ZenMoney blacklist entries to accounts.

Revision ID: 0007_account_blacklists
Revises: 0006_multi_accounts_adjustments
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_account_blacklists"
down_revision: str | Sequence[str] | None = "0006_multi_accounts_adjustments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_zenmoney_blacklist_pattern_lower", table_name="zenmoney_blacklist_entries")
    op.add_column("zenmoney_blacklist_entries", sa.Column("account_id", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE zenmoney_blacklist_entries
        SET account_id = (SELECT account_id FROM zenmoney_settings WHERE id = 1)
        """
    )
    op.execute("DELETE FROM zenmoney_blacklist_entries WHERE account_id IS NULL")
    op.alter_column("zenmoney_blacklist_entries", "account_id", nullable=False)
    op.create_foreign_key(
        "fk_zenmoney_blacklist_account",
        "zenmoney_blacklist_entries",
        "zenmoney_account_configs",
        ["account_id"],
        ["account_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_zenmoney_blacklist_account_pattern_lower",
        "zenmoney_blacklist_entries",
        ["account_id", sa.text("lower(pattern)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_zenmoney_blacklist_account_pattern_lower",
        table_name="zenmoney_blacklist_entries",
    )
    op.drop_constraint(
        "fk_zenmoney_blacklist_account", "zenmoney_blacklist_entries", type_="foreignkey"
    )
    op.execute(
        """
        DELETE FROM zenmoney_blacklist_entries newer
        USING zenmoney_blacklist_entries older
        WHERE lower(newer.pattern) = lower(older.pattern) AND newer.id::text > older.id::text
        """
    )
    op.drop_column("zenmoney_blacklist_entries", "account_id")
    op.create_index(
        "uq_zenmoney_blacklist_pattern_lower",
        "zenmoney_blacklist_entries",
        [sa.text("lower(pattern)")],
        unique=True,
    )
