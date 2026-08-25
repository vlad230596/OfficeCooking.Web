from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models import Base

EXPECTED_TABLES = {
    "import_runs",
    "users",
    "user_contacts",
    "payment_types",
    "payments",
    "cook_templates",
    "template_vote_variants",
    "template_ingredients",
    "cooks",
    "cook_vote_variants",
    "cook_members",
    "cook_member_votes",
    "cook_product_prices",
}


def _constraint_sql(table_name: str) -> str:
    table = Base.metadata.tables[table_name]
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_schema_contains_the_complete_v1_table_set() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_import_run_records_reproducible_publication_state() -> None:
    table = Base.metadata.tables["import_runs"]
    assert not table.c.manifest_checksum.nullable
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["manifest_checksum"]
        for constraint in table.constraints
    )
    assert table.c.started_at.type.timezone is True
    assert table.c.completed_at.type.timezone is True
    assert table.c.completed_at.nullable
    sql = _constraint_sql("import_runs")
    assert "'loading', 'validated', 'published', 'failed', 'rolled_back'" in sql


def test_root_import_entities_have_uuid_primary_keys_and_source_keys() -> None:
    for table_name in ("users", "payment_types", "payments", "cook_templates", "cooks"):
        table = Base.metadata.tables[table_name]
        assert [column.name for column in table.primary_key.columns] == ["id"]
        assert isinstance(table.c.id.type, postgresql.UUID)
        assert not table.c.source_key.nullable
        assert any(
            isinstance(constraint, UniqueConstraint)
            and [column.name for column in constraint.columns] == ["source_key"]
            for constraint in table.constraints
        )


def test_all_ordered_collections_reject_negative_positions() -> None:
    ordered_tables = (
        "user_contacts",
        "template_vote_variants",
        "template_ingredients",
        "cook_vote_variants",
        "cook_members",
        "cook_member_votes",
        "cook_product_prices",
    )
    for table_name in ordered_tables:
        checks = {
            str(constraint.sqltext)
            for constraint in Base.metadata.tables[table_name].constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert "position >= 0" in checks


def test_member_votes_use_two_cross_cook_safe_composite_foreign_keys() -> None:
    table = Base.metadata.tables["cook_member_votes"]
    composite_fks = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint) and len(constraint.columns) == 2
    ]
    targets = {
        tuple(element.target_fullname for element in constraint.elements)
        for constraint in composite_fks
    }
    assert targets == {
        ("cook_members.cook_id", "cook_members.id"),
        ("cook_vote_variants.cook_id", "cook_vote_variants.id"),
    }
    assert {constraint.ondelete for constraint in composite_fks} == {"CASCADE"}
    assert len(table.c.cook_member_id.foreign_keys) == 1


def test_product_cache_status_consistency_is_enforced_by_postgresql_ddl() -> None:
    sql = _constraint_sql("cook_product_prices")
    assert "calculation_status IN ('valid', 'empty', 'error')" in sql
    assert "computed_value IS NULL" in sql
    assert "length(calculation_error) > 0" in sql
    assert "computed_value REAL" in sql


def test_postgresql_specific_column_semantics_compile_as_expected() -> None:
    users_sql = _constraint_sql("users")
    cooks_sql = _constraint_sql("cooks")
    payments_sql = _constraint_sql("payments")
    assert "id UUID NOT NULL" in users_sql
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in users_sql
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in cooks_sql
    assert "registration_date_parsed TIMESTAMP WITHOUT TIME ZONE" in payments_sql
    assert "legacy_filename TEXT NOT NULL" in cooks_sql
    assert Base.metadata.tables["users"].c.updated_at.onupdate is not None
    members_sql = _constraint_sql("cook_members")
    assert "permanent_sale_snapshot REAL NOT NULL" in members_sql


def test_required_query_indexes_and_delete_policies_are_present() -> None:
    index_names = {index.name for table in Base.metadata.tables.values() for index in table.indexes}
    assert {
        "ix_cooks_template_id_cook_date_desc",
        "ix_cook_members_user_id_cook_id",
        "ix_payments_user_id_payment_date",
        "ix_payments_payment_date",
    } <= index_names

    cooks = Base.metadata.tables["cooks"]
    assert next(iter(cooks.c.template_id.foreign_keys)).ondelete == "SET NULL"
    products = Base.metadata.tables["cook_product_prices"]
    assert next(iter(products.c.cook_id.foreign_keys)).ondelete == "CASCADE"
