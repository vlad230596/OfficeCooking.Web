"""Support multiple ZenMoney accounts and audited balance adjustments.

Revision ID: 0006_multi_accounts_adjustments
Revises: 0005_zenmoney_match_rules
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_multi_accounts_adjustments"
down_revision: str | Sequence[str] | None = "0005_zenmoney_match_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "zenmoney_account_configs",
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("account_title", sa.Text(), nullable=False),
        sa.Column("payment_type_id", sa.UUID(), nullable=False),
        sa.Column("server_timestamp", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["payment_type_id"], ["payment_types.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.execute(
        """
        INSERT INTO zenmoney_account_configs
            (account_id, account_title, payment_type_id, server_timestamp, last_sync_at)
        SELECT account_id, account_title, payment_type_id, server_timestamp, last_sync_at
        FROM zenmoney_settings
        ON CONFLICT (account_id) DO NOTHING
        """
    )
    op.create_table(
        "balance_adjustments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("adjustment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.CheckConstraint("amount <> 0", name="amount_nonzero"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="reason_nonempty"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_balance_adjustments_user_date",
        "balance_adjustments",
        ["user_id", "adjustment_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_balance_adjustments_user_date", table_name="balance_adjustments")
    op.drop_table("balance_adjustments")
    op.drop_table("zenmoney_account_configs")
