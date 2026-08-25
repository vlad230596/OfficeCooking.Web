from pathlib import Path
from subprocess import run

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_initial_migration_renders_complete_offline_postgresql_sql() -> None:
    result = run(
        ["uv", "run", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    sql = result.stdout
    assert "CREATE TABLE users" in sql
    assert "CREATE TABLE import_runs" in sql
    assert "CREATE TABLE cook_member_votes" in sql
    assert "CREATE TABLE cook_product_prices" in sql
    assert "FOREIGN KEY(cook_id, cook_vote_variant_id)" in sql
    assert "TIMESTAMP WITH TIME ZONE DEFAULT now()" in sql
    assert "CREATE INDEX ix_cooks_template_id_cook_date_desc" in sql
    assert "INSERT INTO alembic_version" in sql
    assert "ADD COLUMN permanent_sale_snapshot REAL" in sql
    assert "SET permanent_sale_snapshot = users.permanent_sale" in sql


def test_initial_revision_is_immutable_and_does_not_import_live_metadata() -> None:
    revision = (BACKEND_ROOT / "migrations" / "versions" / "0001_initial_schema.py").read_text(
        encoding="utf-8"
    )
    assert "app.models" not in revision
    assert "Base.metadata" not in revision
    assert "create_all" not in revision
    assert "drop_all" not in revision
    assert revision.count("op.create_table(") == 13
