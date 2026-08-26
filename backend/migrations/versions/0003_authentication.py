"""Add password accounts, roles, and revocable sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_authentication"
down_revision: str | Sequence[str] | None = "0002_member_sale_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("role", sa.Text(), server_default="viewer", nullable=False)
    )
    op.add_column(
        "users", sa.Column("auth_enabled", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.create_check_constraint(
        "users_role_allowed", "users", "role IN ('viewer', 'editor', 'admin')"
    )
    op.create_index("uq_users_username_lower", "users", [sa.text("lower(username)")], unique=True)
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("csrf_token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("auth_sessions")
    op.drop_index("uq_users_username_lower", table_name="users")
    op.drop_constraint("users_role_allowed", "users", type_="check")
    op.drop_column("users", "auth_enabled")
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
