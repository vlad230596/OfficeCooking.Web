"""Add secure ZenMoney import and review queue.

Revision ID: 0004_zenmoney_import
Revises: 0003_authentication
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_zenmoney_import"
down_revision: str | Sequence[str] | None = "0003_authentication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("included_in_balance", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_table(
        "zenmoney_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("account_title", sa.Text(), nullable=False),
        sa.Column("payment_type_id", sa.UUID(), nullable=False),
        sa.Column("server_timestamp", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["payment_type_id"], ["payment_types.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="singleton"),
    )
    op.create_table(
        "zenmoney_blacklist_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_zenmoney_blacklist_pattern_lower",
        "zenmoney_blacklist_entries",
        [sa.text("lower(pattern)")],
        unique=True,
    )
    op.create_table(
        "zenmoney_transactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("zenmoney_id", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("changed", sa.BigInteger(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.REAL(), nullable=False),
        sa.Column("payee", sa.Text(), nullable=True),
        sa.Column("original_payee", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("hold", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("decision_source", sa.Text(), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("payment_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status IN ('matched', 'review', 'blacklisted', 'rejected')", name="status_allowed"
        ),
        sa.CheckConstraint(
            "decision_source IN ('automatic', 'manual')", name="decision_source_allowed"
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id"),
        sa.UniqueConstraint("zenmoney_id"),
    )
    op.create_index(
        "ix_zenmoney_transactions_date",
        "zenmoney_transactions",
        [sa.literal_column("transaction_date DESC")],
    )
    op.create_index("ix_zenmoney_transactions_status", "zenmoney_transactions", ["status"])


def downgrade() -> None:
    op.drop_table("zenmoney_transactions")
    op.drop_table("zenmoney_blacklist_entries")
    op.drop_table("zenmoney_settings")
    op.drop_column("payments", "included_in_balance")
