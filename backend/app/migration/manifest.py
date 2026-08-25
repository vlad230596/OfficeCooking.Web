from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

AGGREGATE_ALGORITHM = "sha256(path-utf8 + NUL + size-uint64-big-endian + file-sha256-bytes + NUL)"


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Manifest:
    files: tuple[ManifestEntry, ...]
    checksum: str

    def as_dict(self) -> dict[str, object]:
        return {
            "algorithm": AGGREGATE_ALGORITHM,
            "checksum": self.checksum,
            "files": [asdict(entry) for entry in self.files],
        }


class ManifestMismatchError(ValueError):
    pass


def build_manifest(data_root: Path) -> Manifest:
    root = data_root.resolve(strict=True)
    paths = sorted(
        (path for path in root.rglob("*.json") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    aggregate = hashlib.sha256()
    entries: list[ManifestEntry] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        digest = hashlib.sha256(content).digest()
        entries.append(ManifestEntry(relative, len(content), digest.hex()))
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(len(content).to_bytes(8, byteorder="big", signed=False))
        aggregate.update(digest)
        aggregate.update(b"\0")
    return Manifest(tuple(entries), aggregate.hexdigest())


def verify_manifest(data_root: Path, expected_path: Path) -> Manifest:
    actual = build_manifest(data_root)
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_algorithm = expected.get("aggregateAlgorithm", expected.get("algorithm"))
    expected_checksum = expected.get("sourceTreeSha256", expected.get("checksum"))
    expected_files = expected.get("files")
    actual_files = [asdict(entry) for entry in actual.files]
    if (
        expected_algorithm != AGGREGATE_ALGORITHM
        or expected_checksum != actual.checksum
        or expected_files != actual_files
    ):
        raise ManifestMismatchError(
            "source data does not match the expected manifest: "
            f"expected algorithm/checksum {expected_algorithm!r}/{expected_checksum!r}, "
            f"got {AGGREGATE_ALGORITHM!r}/{actual.checksum!r}"
        )
    return actual
