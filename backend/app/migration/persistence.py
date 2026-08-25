from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import func, select

from app.models import (
    Cook,
    CookMember,
    CookMemberVote,
    CookProductPrice,
    CookTemplate,
    CookVoteVariant,
    ImportRun,
    Payment,
    PaymentType,
    TemplateIngredient,
    TemplateVoteVariant,
    User,
    UserContact,
)

from .transform import MigrationBundle


class SessionLike(Protocol):
    async def scalar(self, statement: Any) -> Any: ...

    def add_all(self, instances: list[Any]) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class NonEmptyTargetError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ImportResult:
    status: str
    written: dict[str, int]
    run_id: uuid.UUID


MODEL_ORDER = (
    ("users", User),
    ("user_contacts", UserContact),
    ("payment_types", PaymentType),
    ("cook_templates", CookTemplate),
    ("template_vote_variants", TemplateVoteVariant),
    ("template_ingredients", TemplateIngredient),
    ("cooks", Cook),
    ("cook_vote_variants", CookVoteVariant),
    ("cook_members", CookMember),
    ("cook_member_votes", CookMemberVote),
    ("cook_product_prices", CookProductPrice),
    ("payments", Payment),
)


async def import_bundle(
    session: SessionLike,
    bundle: MigrationBundle,
    *,
    target_database: str,
) -> ImportResult:
    """Atomically publish a bundle and its durable import-run receipt.

    A failed transaction is fully rolled back, including its ``loading`` receipt;
    consequently this function does not claim to durably record failed attempts.
    """

    try:
        existing = await session.scalar(
            select(ImportRun).where(ImportRun.manifest_checksum == bundle.manifest.checksum)
        )
        if existing is not None:
            if existing.status == "published":
                return ImportResult("already_imported", {}, existing.id)
            raise NonEmptyTargetError(
                "the exact manifest has a non-published durable import run "
                f"with status {existing.status!r}"
            )
        if (await session.scalar(select(func.count()).select_from(ImportRun))) != 0:
            raise NonEmptyTargetError("target belongs to a different source manifest")
        for _name, model in MODEL_ORDER:
            if (await session.scalar(select(func.count()).select_from(model))) != 0:
                raise NonEmptyTargetError("migration requires a completely empty target database")
        started_at = datetime.now(UTC)
        run = ImportRun(
            id=uuid.uuid4(),
            manifest_checksum=bundle.manifest.checksum,
            migrator_version="1",
            alembic_revision="0001_initial_schema",
            calculation_version=1,
            status="loading",
            target_database=target_database,
            started_at=started_at,
            completed_at=None,
        )
        session.add_all([run])
        await session.flush()
        for name, _model in MODEL_ORDER:
            session.add_all(bundle.entities[name])
            # The migration objects intentionally do not carry ORM relationships.
            # Flush each dependency layer so PostgreSQL never receives a child row
            # before the parent table has been populated.
            await session.flush()
        run.status = "published"
        run.completed_at = datetime.now(UTC)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return ImportResult("imported", bundle.counts, run.id)
