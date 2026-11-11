from collections import defaultdict
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts.settlements import (
    PurchaseResponse,
    RepaymentResponse,
    ReplaceSettlementsRequest,
    SettlementEventResponse,
    SettlementsResponse,
)
from app.models import Cook, CookPurchase, CookReimbursement, User
from app.services.cooks import CookNotFoundError, InvalidSnapshotError, VersionConflictError


async def get_settlements(session: AsyncSession, cook_id: UUID) -> SettlementsResponse:
    cook = await session.get(Cook, cook_id)
    if cook is None:
        raise CookNotFoundError("Cook was not found.")
    rows = (
        await session.execute(
            select(CookPurchase, User.name)
            .join(User, User.id == CookPurchase.user_id)
            .where(CookPurchase.cook_id == cook_id)
            .order_by(CookPurchase.position)
        )
    ).all()
    repayments = (
        await session.scalars(
            select(CookReimbursement)
            .join(CookPurchase)
            .where(CookPurchase.cook_id == cook_id)
            .order_by(CookReimbursement.repayment_date, CookReimbursement.id)
        )
    ).all()
    by_purchase = defaultdict(list)
    for repayment in repayments:
        by_purchase[repayment.purchase_id].append(
            RepaymentResponse(
                id=repayment.id, amount=repayment.amount, repayment_date=repayment.repayment_date
            )
        )
    return SettlementsResponse(
        cook_id=cook_id,
        row_version=cook.row_version,
        purchases=[
            PurchaseResponse(
                id=p.id,
                user_id=p.user_id,
                user_name=name,
                amount=p.amount,
                description=p.description,
                mode=p.mode,
                repayments=by_purchase[p.id],
            )
            for p, name in rows
        ],
    )


async def replace_settlements(
    session: AsyncSession, cook_id: UUID, request: ReplaceSettlementsRequest
) -> SettlementsResponse:
    cook = await session.scalar(
        select(Cook)
        .where(Cook.id == cook_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if cook is None:
        raise CookNotFoundError("Cook was not found.")
    if cook.row_version != request.expected_version:
        raise VersionConflictError(
            "Cook was changed by another request.", details={"currentVersion": cook.row_version}
        )
    existing = (
        await session.scalars(select(CookPurchase).where(CookPurchase.cook_id == cook_id))
    ).all()
    old_ids = {p.id for p in existing}
    repayments = (
        await session.scalars(
            select(CookReimbursement).join(CookPurchase).where(CookPurchase.cook_id == cook_id)
        )
    ).all()
    old_repayments = {r.id: r.purchase_id for r in repayments}
    users = set(
        (
            await session.scalars(
                select(User.id).where(User.id.in_({p.user_id for p in request.purchases}))
            )
        ).all()
    )
    if users != {p.user_id for p in request.purchases}:
        raise InvalidSnapshotError("Purchase user was not found.")
    for purchase in request.purchases:
        if purchase.id is not None and purchase.id not in old_ids:
            raise InvalidSnapshotError("Purchase does not belong to this cook.")
        for repayment in purchase.repayments:
            if repayment.id is not None and (
                purchase.id is None or old_repayments.get(repayment.id) != purchase.id
            ):
                raise InvalidSnapshotError("Repayment does not belong to this purchase.")
    await session.execute(
        delete(CookReimbursement).where(CookReimbursement.purchase_id.in_(old_ids))
    )
    await session.execute(delete(CookPurchase).where(CookPurchase.cook_id == cook_id))
    await session.flush()
    for position, purchase in enumerate(request.purchases):
        purchase_id = purchase.id or uuid4()
        session.add(
            CookPurchase(
                id=purchase_id,
                cook_id=cook_id,
                user_id=purchase.user_id,
                position=position,
                amount=purchase.amount,
                description=purchase.description,
                mode=purchase.mode,
            )
        )
        await session.flush()
        for repayment in purchase.repayments:
            session.add(
                CookReimbursement(
                    id=repayment.id or uuid4(),
                    purchase_id=purchase_id,
                    amount=repayment.amount,
                    repayment_date=repayment.repayment_date,
                )
            )
    cook.row_version += 1
    await session.commit()
    return await get_settlements(session, cook_id)


async def load_settlement_events(
    session: AsyncSession, date_from: date, date_to: date
) -> list[tuple[UUID, SettlementEventResponse]]:
    purchases = await session.execute(
        select(
            CookPurchase,
            Cook.cook_date,
            func.coalesce(func.sum(CookReimbursement.amount), 0),
        )
        .join(Cook)
        .outerjoin(
            CookReimbursement,
            and_(
                CookReimbursement.purchase_id == CookPurchase.id,
                CookPurchase.mode == "separate",
                CookReimbursement.repayment_date <= date_to,
            ),
        )
        .where(Cook.cook_date.between(date_from, date_to))
        .group_by(CookPurchase.id, Cook.cook_date)
    )
    # Reimbursements remain visible even when their cook lies outside the period.
    repayments = await session.execute(
        select(CookReimbursement, CookPurchase)
        .join(CookPurchase)
        .where(CookReimbursement.repayment_date.between(date_from, date_to))
    )
    events = [
        (
            p.user_id,
            SettlementEventResponse(
                id=p.id,
                cook_id=p.cook_id,
                event_date=day,
                kind="purchase",
                amount=p.amount,
                description=p.description,
                mode=p.mode,
                separate_owed=p.amount - repaid if p.mode == "separate" else None,
            ),
        )
        for p, day, repaid in purchases
    ]
    events.extend(
        (
            p.user_id,
            SettlementEventResponse(
                id=r.id,
                cook_id=p.cook_id,
                event_date=r.repayment_date,
                kind="reimbursement",
                amount=r.amount,
                description=p.description,
                mode=p.mode,
            ),
        )
        for r, p in repayments
    )
    return sorted(events, key=lambda pair: (pair[1].event_date, pair[1].kind, str(pair[1].id)))
