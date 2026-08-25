from types import SimpleNamespace
from typing import Any

import pytest

from app.migration.manifest import Manifest
from app.migration.persistence import MODEL_ORDER, NonEmptyTargetError, import_bundle
from app.migration.transform import MigrationBundle, stable_uuid


class FakeSession:
    def __init__(self, scalars: list[Any] | None = None, *, fail_commit: bool = False) -> None:
        self.scalars = iter(scalars or [None, 0, *([0] * 12)])
        self.fail_commit = fail_commit
        self.added: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    async def scalar(self, _statement: Any) -> int:
        return next(self.scalars)

    def add_all(self, instances: list[Any]) -> None:
        self.added.extend(instances)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("database failure")

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture(scope="module")
def bundle() -> MigrationBundle:
    return MigrationBundle(
        manifest=Manifest((), "synthetic-manifest"),
        entities={name: [] for name, _model in MODEL_ORDER},
        user_ids={0: stable_uuid("users:0")},
    )


@pytest.mark.asyncio
async def test_import_writes_in_dependency_order_and_commits_once(bundle) -> None:
    session = FakeSession()

    result = await import_bundle(session, bundle, target_database="officecook_test")

    assert result.status == "imported"
    assert session.commits == 1
    assert session.rollbacks == 0
    assert session.flushes == 13
    assert len(session.added) == sum(bundle.counts.values()) + 1
    run = session.added[0]
    assert run.id == result.run_id
    assert run.manifest_checksum == bundle.manifest.checksum
    assert run.target_database == "officecook_test"
    assert run.status == "published"
    assert run.started_at is not None
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_nonempty_target_is_explicitly_refused_and_rolled_back(bundle) -> None:
    session = FakeSession([None, 0, 0, 0, 1])

    with pytest.raises(NonEmptyTargetError, match="completely empty"):
        await import_bundle(session, bundle, target_database="officecook_test")

    assert session.commits == 0
    assert session.rollbacks == 1
    assert session.added == []


@pytest.mark.asyncio
async def test_exact_published_manifest_is_already_imported_without_db_changes(bundle) -> None:
    run_id = bundle.user_ids[0]
    session = FakeSession([SimpleNamespace(status="published", id=run_id)])

    result = await import_bundle(session, bundle, target_database="officecook_test")

    assert result.status == "already_imported"
    assert result.run_id == run_id
    assert session.commits == session.rollbacks == 0
    assert session.added == []


@pytest.mark.asyncio
async def test_changed_manifest_is_refused_without_db_changes(bundle) -> None:
    session = FakeSession([None, 1])

    with pytest.raises(NonEmptyTargetError, match="different source manifest"):
        await import_bundle(session, bundle, target_database="officecook_test")

    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_exact_nonpublished_run_is_refused(bundle) -> None:
    session = FakeSession([SimpleNamespace(status="failed", id=bundle.user_ids[0])])

    with pytest.raises(NonEmptyTargetError, match="non-published"):
        await import_bundle(session, bundle, target_database="officecook_test")

    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_commit_failure_rolls_back(bundle) -> None:
    session = FakeSession(fail_commit=True)

    with pytest.raises(RuntimeError, match="database failure"):
        await import_bundle(session, bundle, target_database="officecook_test")

    assert session.commits == 1
    assert session.rollbacks == 1
