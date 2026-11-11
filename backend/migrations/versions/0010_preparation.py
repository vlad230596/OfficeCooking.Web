"""Add independent preparation plans and template presets."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_preparation"
down_revision = "0009_cook_settlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "template_preparations",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["cook_templates.id"], ondelete="CASCADE"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
    )
    op.create_table(
        "cook_preparations",
        sa.Column("cook_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("groups", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["cook_id"], ["cooks.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("cook_preparations")
    op.drop_table("template_preparations")
