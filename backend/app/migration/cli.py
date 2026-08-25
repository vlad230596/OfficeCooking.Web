from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.database import create_engine, create_session_factory

from .json_reader import SourceJsonError
from .manifest import build_manifest, verify_manifest
from .persistence import import_bundle
from .transform import transform_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate legacy OfficeCook JSON")
    parser.add_argument("command", choices=("validate", "dry-run", "import"))
    parser.add_argument("--data", type=Path, required=True, help="read-only legacy data directory")
    parser.add_argument("--manifest", type=Path, help="expected manifest to verify before reading")
    parser.add_argument("--report", type=Path, help="write the structured report as UTF-8 JSON")
    return parser


async def _import(bundle):
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            target_database = settings.build_database_url().database or ""
            return await import_bundle(session, bundle, target_database=target_database)
    finally:
        await engine.dispose()


def _write_report(report: dict[str, object], report_path: Path | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
    # Windows terminals may still expose a legacy code page. ASCII-escaped JSON
    # remains valid machine-readable output while the report file stays UTF-8.
    print(json.dumps(report, ensure_ascii=True, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = None
    try:
        manifest = (
            verify_manifest(args.data, args.manifest)
            if args.manifest is not None
            else build_manifest(args.data)
        )
        bundle = transform_snapshot(args.data, manifest=manifest)
        if args.command == "import":
            import_result = asyncio.run(_import(bundle))
            status = import_result.status
        else:
            status = "dry_run" if args.command == "dry-run" else "validated"
        report = bundle.report(status=status)
        if args.command == "import":
            report["run_id"] = str(import_result.run_id)
    except Exception as exc:  # CLI boundary: always leave a machine-readable failure report.
        source_path = str(exc.path) if isinstance(exc, SourceJsonError) else ""
        report = {
            "schema_version": "office-cook-migration-report/v1",
            "run_id": str(uuid.uuid4()),
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "failed",
            "durable_import_run": False,
            "durable_status": None,
            "manifest_checksum": manifest.checksum if manifest is not None else None,
            "migrator_version": "1",
            "alembic_revision": "0001_initial_schema",
            "calculation_version": 1,
            "entities": {},
            "legacy_mappings": {"users": {}, "payment_types": {}},
            "issues": [
                {
                    "source_path": source_path,
                    "json_path": "$",
                    "reason": str(exc),
                    "kind": "validation",
                }
            ],
        }
        _write_report(report, args.report)
        return 1
    _write_report(report, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
