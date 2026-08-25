"""Create the initial OfficeCookAssistant schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("manifest_checksum", sa.Text(), nullable=False),
        sa.Column("migrator_version", sa.Text(), nullable=False),
        sa.Column("alembic_revision", sa.Text(), nullable=False),
        sa.Column("calculation_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("target_database", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "calculation_version >= 1",
            name=op.f("ck_import_runs_calculation_version_positive"),
        ),
        sa.CheckConstraint(
            "status IN ('loading', 'validated', 'published', 'failed', 'rolled_back')",
            name=op.f("ck_import_runs_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_runs")),
        sa.UniqueConstraint("manifest_checksum", name=op.f("uq_import_runs_manifest_checksum")),
    )
    op.create_table(
        "cook_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("legacy_name", sa.Text(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("is_multivote", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cook_templates")),
        sa.UniqueConstraint("legacy_name", name=op.f("uq_cook_templates_legacy_name")),
        sa.UniqueConstraint("source_key", name=op.f("uq_cook_templates_source_key")),
    )
    op.create_table(
        "payment_types",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("legacy_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_types")),
        sa.UniqueConstraint("legacy_id", name=op.f("uq_payment_types_legacy_id")),
        sa.UniqueConstraint("source_key", name=op.f("uq_payment_types_source_key")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("legacy_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("permanent_sale", sa.REAL(), server_default=sa.text("1.0"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("legacy_id", name=op.f("uq_users_legacy_id")),
        sa.UniqueConstraint("source_key", name=op.f("uq_users_source_key")),
    )
    op.create_table(
        "cooks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cook_date", sa.Date(), nullable=False),
        sa.Column("legacy_filename", sa.Text(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column("type_snapshot", sa.Text(), nullable=False),
        sa.Column("sale", sa.REAL(), nullable=False),
        sa.Column("total_price_cached", sa.REAL(), nullable=True),
        sa.Column("calculation_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "calculation_version >= 1", name=op.f("ck_cooks_calculation_version_positive")
        ),
        sa.CheckConstraint("row_version >= 1", name=op.f("ck_cooks_row_version_positive")),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["cook_templates.id"],
            name=op.f("fk_cooks_template_id_cook_templates"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cooks")),
        sa.UniqueConstraint("cook_date", name=op.f("uq_cooks_cook_date")),
        sa.UniqueConstraint("legacy_filename", name=op.f("uq_cooks_legacy_filename")),
        sa.UniqueConstraint("source_key", name=op.f("uq_cooks_source_key")),
    )
    op.create_index(
        "ix_cooks_template_id_cook_date_desc",
        "cooks",
        ["template_id", sa.literal_column("cook_date DESC")],
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("legacy_position", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("payment_type_id", sa.UUID(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_date_raw", sa.Text(), nullable=False),
        sa.Column("registration_date_raw", sa.Text(), nullable=True),
        sa.Column("registration_date_parsed", sa.DateTime(), nullable=True),
        sa.Column("sum", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_type_id"],
            ["payment_types.id"],
            name=op.f("fk_payments_payment_type_id_payment_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_payments_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("legacy_position", name=op.f("uq_payments_legacy_position")),
        sa.UniqueConstraint("source_key", name=op.f("uq_payments_source_key")),
    )
    op.create_index("ix_payments_payment_date", "payments", ["payment_date"])
    op.create_index("ix_payments_user_id_payment_date", "payments", ["user_id", "payment_date"])
    op.create_table(
        "template_ingredients",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_template_ingredients_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["cook_templates.id"],
            name=op.f("fk_template_ingredients_template_id_cook_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_ingredients")),
        sa.UniqueConstraint(
            "template_id", "position", name=op.f("uq_template_ingredients_template_id_position")
        ),
    )
    op.create_table(
        "template_vote_variants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value", sa.REAL(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_template_vote_variants_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["cook_templates.id"],
            name=op.f("fk_template_vote_variants_template_id_cook_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_vote_variants")),
        sa.UniqueConstraint(
            "template_id", "position", name=op.f("uq_template_vote_variants_template_id_position")
        ),
    )
    op.create_table(
        "user_contacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name=op.f("ck_user_contacts_position_nonnegative")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_contacts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_contacts")),
        sa.UniqueConstraint("user_id", "position", name=op.f("uq_user_contacts_user_id_position")),
    )
    op.create_table(
        "cook_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cook_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("position >= 0", name=op.f("ck_cook_members_position_nonnegative")),
        sa.ForeignKeyConstraint(
            ["cook_id"],
            ["cooks.id"],
            name=op.f("fk_cook_members_cook_id_cooks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_cook_members_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cook_members")),
        sa.UniqueConstraint("cook_id", "id", name=op.f("uq_cook_members_cook_id_id")),
        sa.UniqueConstraint("cook_id", "position", name=op.f("uq_cook_members_cook_id_position")),
        sa.UniqueConstraint("cook_id", "user_id", name=op.f("uq_cook_members_cook_id_user_id")),
    )
    op.create_index("ix_cook_members_user_id_cook_id", "cook_members", ["user_id", "cook_id"])
    op.create_table(
        "cook_product_prices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cook_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("expression", sa.Text(), nullable=True),
        sa.Column("computed_value", sa.REAL(), nullable=True),
        sa.Column("calculation_status", sa.Text(), nullable=False),
        sa.Column("calculation_error", sa.Text(), nullable=True),
        sa.Column("calculation_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "((calculation_status IN ('valid', 'empty') "
            "AND computed_value IS NOT NULL AND calculation_error IS NULL) OR "
            "(calculation_status = 'error' AND computed_value IS NULL "
            "AND calculation_error IS NOT NULL AND length(calculation_error) > 0))",
            name=op.f("ck_cook_product_prices_calculation_fields_consistent"),
        ),
        sa.CheckConstraint(
            "calculation_status IN ('valid', 'empty', 'error')",
            name=op.f("ck_cook_product_prices_calculation_status_allowed"),
        ),
        sa.CheckConstraint(
            "calculation_version >= 1",
            name=op.f("ck_cook_product_prices_calculation_version_positive"),
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_cook_product_prices_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["cook_id"],
            ["cooks.id"],
            name=op.f("fk_cook_product_prices_cook_id_cooks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cook_product_prices")),
        sa.UniqueConstraint(
            "cook_id", "position", name=op.f("uq_cook_product_prices_cook_id_position")
        ),
    )
    op.create_table(
        "cook_vote_variants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cook_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value", sa.REAL(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_cook_vote_variants_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["cook_id"],
            ["cooks.id"],
            name=op.f("fk_cook_vote_variants_cook_id_cooks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cook_vote_variants")),
        sa.UniqueConstraint("cook_id", "id", name=op.f("uq_cook_vote_variants_cook_id_id")),
        sa.UniqueConstraint(
            "cook_id", "position", name=op.f("uq_cook_vote_variants_cook_id_position")
        ),
    )
    op.create_table(
        "cook_member_votes",
        sa.Column("cook_id", sa.UUID(), nullable=False),
        sa.Column("cook_member_id", sa.UUID(), nullable=False),
        sa.Column("cook_vote_variant_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name=op.f("ck_cook_member_votes_position_nonnegative")),
        sa.ForeignKeyConstraint(
            ["cook_id", "cook_member_id"],
            ["cook_members.cook_id", "cook_members.id"],
            name=op.f("fk_cook_member_votes_cook_id_cook_member_id_cook_members"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cook_id", "cook_vote_variant_id"],
            ["cook_vote_variants.cook_id", "cook_vote_variants.id"],
            name=op.f("fk_cook_member_votes_cook_id_cook_vote_variant_id_cook_vote_variants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cook_member_id", "position", name=op.f("pk_cook_member_votes")),
    )


def downgrade() -> None:
    op.drop_table("cook_member_votes")
    op.drop_table("cook_vote_variants")
    op.drop_table("cook_product_prices")
    op.drop_index("ix_cook_members_user_id_cook_id", table_name="cook_members")
    op.drop_table("cook_members")
    op.drop_table("user_contacts")
    op.drop_table("template_vote_variants")
    op.drop_table("template_ingredients")
    op.drop_index("ix_payments_user_id_payment_date", table_name="payments")
    op.drop_index("ix_payments_payment_date", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_cooks_template_id_cook_date_desc", table_name="cooks")
    op.drop_table("cooks")
    op.drop_table("users")
    op.drop_table("payment_types")
    op.drop_table("cook_templates")
    op.drop_table("import_runs")
