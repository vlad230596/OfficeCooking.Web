"""Track participant purchases and organizer reimbursements."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_cook_settlements"
down_revision = "0008_tbank_system_filters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cook_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint("position >= 0", name="position_nonnegative"),
        sa.CheckConstraint("mode IN ('offset', 'separate')", name="mode_allowed"),
        sa.UniqueConstraint("cook_id", "position"),
    )
    op.create_index("ix_cook_purchases_user_cook", "cook_purchases", ["user_id", "cook_id"])
    op.create_table(
        "cook_reimbursements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "purchase_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cook_purchases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("repayment_date", sa.Date(), nullable=False),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
    )
    op.create_index("ix_cook_reimbursements_date", "cook_reimbursements", ["repayment_date"])
    op.create_index(
        "ix_cook_reimbursements_purchase_date",
        "cook_reimbursements",
        ["purchase_id", "repayment_date"],
    )


def downgrade() -> None:
    op.drop_table("cook_reimbursements")
    op.drop_table("cook_purchases")
