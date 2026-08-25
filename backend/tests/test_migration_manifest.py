import json
from pathlib import Path

import pytest

from app.migration.cli import main
from app.migration.json_reader import SourceJsonError, read_json
from app.migration.manifest import ManifestMismatchError, build_manifest, verify_manifest


def test_manifest_aggregate_includes_big_endian_uint64_size(tmp_path: Path) -> None:
    import hashlib

    source = tmp_path / "data"
    source.mkdir()
    content = b"{}"
    (source / "a.json").write_bytes(content)
    digest = hashlib.sha256(content).digest()
    expected = hashlib.sha256(
        b"a.json\0" + len(content).to_bytes(8, "big") + digest + b"\0"
    ).hexdigest()

    manifest = build_manifest(source)

    assert manifest.checksum == expected
    assert "size-uint64-big-endian" in manifest.as_dict()["algorithm"]


def test_manifest_detects_a_changed_byte(tmp_path: Path) -> None:
    source = tmp_path / "data"
    source.mkdir()
    (source / "a.json").write_text("{}", encoding="utf-8")
    manifest = build_manifest(source)
    expected = tmp_path / "manifest.json"
    expected.write_text(json.dumps(manifest.as_dict()), encoding="utf-8")
    (source / "a.json").write_text("{ }", encoding="utf-8")

    with pytest.raises(ManifestMismatchError):
        verify_manifest(source, expected)


def test_only_template_reader_tolerates_trailing_commas(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"value": [1,], "literal": ",]"}', encoding="utf-8")

    with pytest.raises(SourceJsonError):
        read_json(source)
    assert read_json(source, allow_trailing_commas=True) == {"value": [1], "literal": ",]"}


def test_reader_rejects_duplicate_keys_even_in_tolerant_mode(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"a": 1, "a": 2,}', encoding="utf-8")

    with pytest.raises(SourceJsonError, match="duplicate object key"):
        read_json(source, allow_trailing_commas=True)


def test_cli_failure_is_also_a_structured_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "data"
    source.mkdir()
    (source / "Users.json").write_text("not json", encoding="utf-8")
    report_path = tmp_path / "failed.json"

    assert main(["validate", "--data", str(source), "--report", str(report_path)]) == 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["durable_import_run"] is False
    assert report["durable_status"] is None
    assert report["issues"][0]["source_path"].endswith("Users.json")
    assert report["issues"][0]["json_path"] == "$"
    assert "Expecting value" in report["issues"][0]["reason"]
    capsys.readouterr()
