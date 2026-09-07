"""Balance aggregation and bounded-query persistence adapter."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts import (
    BalanceAdjustmentResponse,
    BalanceCookResponse,
    BalancePaymentResponse,
    BalancePaymentTypeResponse,
    BalancesResponse,
    CloseBalanceAdjustmentRequest,
    CloseBalancePreviewResponse,
    CreateBalanceAdjustmentRequest,
    CreateBalancePaymentRequest,
    OrderingMetadata,
    SortField,
    UserBalanceDetailResponse,
    UserBalanceResponse,
    WeekBalanceResponse,
)
from app.domain.legacy_calculation import LegacyCalculationError, ceil_to_5, float32
from app.models import (
    BalanceAdjustment,
    Cook,
    CookMember,
    CookMemberVote,
    CookVoteVariant,
    Payment,
    PaymentType,
    User,
    ZenMoneyTransaction,
)


class BalanceDataError(RuntimeError):
    """Stored data cannot produce a safe Legacy balance."""


class UserNotFoundError(LookupError):
    pass


class PaymentNotFoundError(LookupError):
    pass


class PaymentTypeNotFoundError(LookupError):
    pass


class BalanceChangedError(RuntimeError):
    pass


class ZeroBalanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BalanceUser:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class PaymentTotal:
    user_id: UUID
    payment_date: date
    amount: int


@dataclass(frozen=True, slots=True)
class CookCharge:
    user_id: UUID
    cook_date: date
    amount: int
    cook_id: UUID | None = None
    title: str = ""


@dataclass(frozen=True, slots=True)
class AdjustmentTotal:
    user_id: UUID
    adjustment_date: date
    amount: int


@dataclass(slots=True)
class _MutableWeek:
    positive: int = 0
    negative: int = 0
    cooks_count: int = 0
    adjustment: int = 0


@dataclass(frozen=True, slots=True)
class AggregatedUserBalance:
    user: BalanceUser
    positive: int
    negative: int
    cooks_count: int
    cumulative_balance: int
    adjustments: int
    weeks: tuple[WeekBalanceResponse, ...]


@dataclass(frozen=True, slots=True)
class BalanceCookMember:
    cook_id: UUID
    cook_date: date
    total_price: float | None
    cook_sale: float
    member_id: UUID
    user_id: UUID
    position: int
    active: bool
    permanent_sale: float
    type_snapshot: str


def legacy_week(value: date) -> tuple[int, int]:
    """GregorianCalendar.GetWeekOfYear(FirstDay, Monday) with date.Year."""

    january_first = value.replace(month=1, day=1)
    week = ((value.timetuple().tm_yday - 1 + january_first.weekday()) // 7) + 1
    return value.year, week


def legacy_week_display(year: int, week: int) -> str:
    january_first = date(year, 1, 1)
    raw_start = january_first + timedelta(days=7 * (week - 1) - january_first.weekday())
    start = max(raw_start, january_first)
    end = min(raw_start + timedelta(days=6), date(year, 12, 31))
    return f"{start:%d.%m}–{end:%d.%m.%Y}"


def aggregate_balances(
    users: Sequence[BalanceUser],
    payments: Iterable[PaymentTotal],
    charges: Iterable[CookCharge],
    date_from: date,
    date_to: date,
    adjustments: Iterable[AdjustmentTotal] = (),
) -> tuple[AggregatedUserBalance, ...]:
    """Aggregate inclusive-range events using the Legacy week identity."""

    known_users = {user.id for user in users}
    weeks: dict[UUID, dict[tuple[int, int], _MutableWeek]] = {user.id: {} for user in users}

    for payment in payments:
        if payment.user_id not in known_users or not date_from <= payment.payment_date <= date_to:
            continue
        key = legacy_week(payment.payment_date)
        value = weeks[payment.user_id].setdefault(key, _MutableWeek())
        value.positive += payment.amount

    for charge in charges:
        if charge.user_id not in known_users or not date_from <= charge.cook_date <= date_to:
            continue
        key = legacy_week(charge.cook_date)
        value = weeks[charge.user_id].setdefault(key, _MutableWeek())
        value.negative += charge.amount
        value.cooks_count += 1

    for adjustment in adjustments:
        if (
            adjustment.user_id not in known_users
            or not date_from <= adjustment.adjustment_date <= date_to
        ):
            continue
        key = legacy_week(adjustment.adjustment_date)
        weeks[adjustment.user_id].setdefault(key, _MutableWeek()).adjustment += adjustment.amount

    result: list[AggregatedUserBalance] = []
    for user in users:
        cumulative = 0
        week_responses: list[WeekBalanceResponse] = []
        total_positive = total_negative = total_cooks = total_adjustments = 0
        for (year, week), value in sorted(weeks[user.id].items()):
            weekly_delta = value.positive - value.negative + value.adjustment
            cumulative += weekly_delta
            total_positive += value.positive
            total_negative += value.negative
            total_cooks += value.cooks_count
            total_adjustments += value.adjustment
            week_responses.append(
                WeekBalanceResponse(
                    year=year,
                    week=week,
                    display=legacy_week_display(year, week),
                    positive=value.positive,
                    negative=value.negative,
                    cooks_count=value.cooks_count,
                    weekly_delta=weekly_delta,
                    cumulative_balance=cumulative,
                    adjustment=value.adjustment,
                )
            )
        result.append(
            AggregatedUserBalance(
                user=user,
                positive=total_positive,
                negative=total_negative,
                cooks_count=total_cooks,
                cumulative_balance=cumulative,
                adjustments=total_adjustments,
                weeks=tuple(week_responses),
            )
        )
    return tuple(result)


def calculate_cook_charges(
    member_rows: Sequence[BalanceCookMember], vote_rows: Iterable[tuple[UUID, int, float]]
) -> tuple[CookCharge, ...]:
    votes_by_member: dict[UUID, list[tuple[int, float]]] = defaultdict(list)
    for member_id, position, value in vote_rows:
        votes_by_member[member_id].append((position, value))
    for values in votes_by_member.values():
        values.sort(key=lambda item: item[0])

    cooks: dict[UUID, list[BalanceCookMember]] = {}
    for row in member_rows:
        cooks.setdefault(row.cook_id, []).append(row)

    charges: list[CookCharge] = []
    try:
        for cook_id, members in cooks.items():
            members.sort(key=lambda item: item.position)
            total_price = members[0].total_price
            if total_price is None:
                raise BalanceDataError(f"cook {cook_id} has no cached total")
            effective: list[tuple[BalanceCookMember, float]] = []
            total_weight = 0.0
            for member in members:
                vote_weight = 0.0
                for _, vote_value in votes_by_member.get(member.member_id, []):
                    vote_weight = float32(float32(vote_weight) + float32(vote_value))
                weight = float32(float32(vote_weight) * float32(member.permanent_sale))
                if member.active:
                    weight = float32(float32(weight) * float32(member.cook_sale))
                total_weight = float32(float32(total_weight) + weight)
                effective.append((member, weight))
            if total_weight == 0.0:
                raise BalanceDataError(f"cook {cook_id} has zero effective weight")
            unit_price = float32(float32(total_price) / total_weight)
            for member, weight in effective:
                amount = ceil_to_5(float32(unit_price * weight))
                charges.append(
                    CookCharge(
                        member.user_id,
                        member.cook_date,
                        amount,
                        member.cook_id,
                        member.type_snapshot,
                    )
                )
    except LegacyCalculationError as exc:
        raise BalanceDataError(str(exc)) from exc
    return tuple(charges)


class BalanceService:
    """Read balances with four set-based queries, independent of user count."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_balances(
        self, date_from: date, date_to: date, *, non_zero_only: bool = False
    ) -> BalancesResponse:
        aggregated = await self._load(date_from, date_to)
        if non_zero_only:
            aggregated = tuple(item for item in aggregated if item.cumulative_balance != 0)
        return BalancesResponse(
            date_from=date_from,
            date_to=date_to,
            items=[
                UserBalanceResponse(
                    user_id=item.user.id,
                    user_name=item.user.name,
                    positive=item.positive,
                    negative=item.negative,
                    cooks_count=item.cooks_count,
                    cumulative_balance=item.cumulative_balance,
                    adjustments=item.adjustments,
                )
                for item in aggregated
            ],
            ordering=OrderingMetadata(
                fields=[
                    SortField(field="userName", direction="asc"),
                    SortField(field="userId", direction="asc"),
                ]
            ),
        )

    async def get_user_balance(
        self, user_id: UUID, date_from: date, date_to: date
    ) -> UserBalanceDetailResponse:
        aggregated = await self._load(date_from, date_to)
        item = next((value for value in aggregated if value.user.id == user_id), None)
        if item is None:
            raise UserNotFoundError(str(user_id))
        payments, charges, adjustments = await self._load_user_activity(user_id, date_from, date_to)
        payment_types = (
            await self._session.execute(
                select(PaymentType).where(PaymentType.enabled.is_(True)).order_by(PaymentType.name)
            )
        ).scalars()
        payments_by_week: dict[tuple[int, int], list[BalancePaymentResponse]] = defaultdict(list)
        for payment in payments:
            payments_by_week[legacy_week(payment.payment_date)].append(payment)
        cooks_by_week: dict[tuple[int, int], list[BalanceCookResponse]] = defaultdict(list)
        for charge in charges:
            cooks_by_week[legacy_week(charge.cook_date)].append(charge)
        adjustments_by_week: dict[tuple[int, int], list[BalanceAdjustmentResponse]] = defaultdict(
            list
        )
        for adjustment in adjustments:
            adjustments_by_week[legacy_week(adjustment.adjustment_date)].append(adjustment)
        return UserBalanceDetailResponse(
            user_id=item.user.id,
            user_name=item.user.name,
            date_from=date_from,
            date_to=date_to,
            weeks=[
                week.model_copy(
                    update={
                        "payments": payments_by_week[(week.year, week.week)],
                        "cooks": cooks_by_week[(week.year, week.week)],
                        "adjustments": adjustments_by_week[(week.year, week.week)],
                    }
                )
                for week in item.weeks
            ],
            payment_types=[
                BalancePaymentTypeResponse(id=value.id, name=value.name) for value in payment_types
            ],
            ordering=OrderingMetadata(
                fields=[
                    SortField(field="year", direction="asc"),
                    SortField(field="week", direction="asc"),
                ]
            ),
        )

    async def create_payment(self, user_id: UUID, request: CreateBalancePaymentRequest) -> None:
        if await self._session.get(User, user_id) is None:
            raise UserNotFoundError(str(user_id))
        payment_type = await self._session.get(PaymentType, request.payment_type_id)
        if payment_type is None or not payment_type.enabled:
            raise PaymentTypeNotFoundError(str(request.payment_type_id))
        payment_id = uuid4()
        max_position = await self._session.scalar(select(func.max(Payment.legacy_position)))
        self._session.add(
            Payment(
                id=payment_id,
                legacy_position=(max_position if max_position is not None else -1) + 1,
                user_id=user_id,
                payment_type_id=payment_type.id,
                payment_date=request.payment_date,
                payment_date_raw=request.payment_date.strftime("%d.%m.%Y"),
                registration_date_raw=None,
                registration_date_parsed=None,
                sum=request.amount,
                comment=request.comment.strip(),
                source_key=f"manual:{payment_id}",
                included_in_balance=True,
            )
        )
        await self._session.commit()

    async def delete_payment(self, user_id: UUID, payment_id: UUID) -> None:
        payment = await self._session.scalar(
            select(Payment).where(Payment.id == payment_id, Payment.user_id == user_id)
        )
        if payment is None:
            raise PaymentNotFoundError(str(payment_id))
        transaction = await self._session.scalar(
            select(ZenMoneyTransaction).where(ZenMoneyTransaction.payment_id == payment.id)
        )
        if transaction is not None:
            transaction.payment_id = None
            transaction.user_id = None
            transaction.status = "rejected"
            transaction.decision_source = "manual"
            transaction.match_reason = "payment deleted manually"
        await self._session.delete(payment)
        await self._session.commit()

    async def close_balance_preview(
        self, user_id: UUID, adjustment_date: date
    ) -> CloseBalancePreviewResponse:
        balance = await self._balance_on(user_id, adjustment_date)
        return CloseBalancePreviewResponse(
            adjustment_date=adjustment_date,
            balance_before=balance,
            adjustment_amount=-balance,
        )

    async def close_balance(
        self,
        user_id: UUID,
        request: CloseBalanceAdjustmentRequest,
        created_by_user_id: UUID | None,
    ) -> BalanceAdjustmentResponse:
        balance = await self._balance_on(user_id, request.adjustment_date)
        if balance != request.expected_balance:
            raise BalanceChangedError("balance changed while the adjustment was being confirmed")
        if balance == 0:
            raise ZeroBalanceError("balance is already zero")
        author = await self._session.get(User, created_by_user_id) if created_by_user_id else None
        value = BalanceAdjustment(
            id=uuid4(),
            user_id=user_id,
            adjustment_date=request.adjustment_date,
            amount=-balance,
            balance_before=balance,
            reason=request.reason.strip(),
            created_at=datetime.now(UTC),
            created_by_user_id=created_by_user_id,
        )
        self._session.add(value)
        await self._session.commit()
        return BalanceAdjustmentResponse(
            id=value.id,
            adjustment_date=value.adjustment_date,
            amount=value.amount,
            balance_before=value.balance_before,
            reason=value.reason,
            created_at=value.created_at,
            created_by_name=author.name if author else None,
        )

    async def create_adjustment(
        self,
        user_id: UUID,
        request: CreateBalanceAdjustmentRequest,
        created_by_user_id: UUID | None,
    ) -> BalanceAdjustmentResponse:
        values = await self._load(request.balance_date_from, request.balance_date_to)
        item = next((value for value in values if value.user.id == user_id), None)
        if item is None:
            raise UserNotFoundError(str(user_id))
        if item.cumulative_balance != request.expected_balance:
            raise BalanceChangedError("balance changed while the adjustment was being confirmed")
        author = await self._session.get(User, created_by_user_id) if created_by_user_id else None
        value = BalanceAdjustment(
            id=uuid4(),
            user_id=user_id,
            adjustment_date=request.adjustment_date,
            amount=request.amount,
            balance_before=item.cumulative_balance,
            reason=request.reason.strip(),
            created_at=datetime.now(UTC),
            created_by_user_id=created_by_user_id,
        )
        self._session.add(value)
        await self._session.commit()
        return BalanceAdjustmentResponse(
            id=value.id,
            adjustment_date=value.adjustment_date,
            amount=value.amount,
            balance_before=value.balance_before,
            reason=value.reason,
            created_at=value.created_at,
            created_by_name=author.name if author else None,
        )

    async def _balance_on(self, user_id: UUID, adjustment_date: date) -> int:
        values = await self._load(date(1900, 1, 1), adjustment_date)
        item = next((value for value in values if value.user.id == user_id), None)
        if item is None:
            raise UserNotFoundError(str(user_id))
        return item.cumulative_balance

    async def _load_user_activity(
        self, user_id: UUID, date_from: date, date_to: date
    ) -> tuple[
        list[BalancePaymentResponse], list[BalanceCookResponse], list[BalanceAdjustmentResponse]
    ]:
        payment_rows = await self._session.execute(
            select(
                Payment.id,
                Payment.payment_date,
                Payment.sum,
                Payment.comment,
                Payment.source_key,
                PaymentType.name.label("payment_type_name"),
                ZenMoneyTransaction.id.label("zenmoney_transaction_id"),
            )
            .join(PaymentType, PaymentType.id == Payment.payment_type_id)
            .outerjoin(ZenMoneyTransaction, ZenMoneyTransaction.payment_id == Payment.id)
            .where(
                Payment.user_id == user_id,
                Payment.included_in_balance.is_(True),
                Payment.payment_date.between(date_from, date_to),
            )
            .order_by(Payment.payment_date, Payment.id)
        )
        payments = [
            BalancePaymentResponse(
                id=row.id,
                payment_date=row.payment_date,
                amount=row.sum,
                payment_type_name=row.payment_type_name,
                comment=row.comment,
                source=(
                    "ZenMoney"
                    if row.zenmoney_transaction_id
                    else "Вручную"
                    if row.source_key.startswith("manual:")
                    else "Старый импорт"
                ),
            )
            for row in payment_rows
        ]
        member_rows = await self._session.execute(self._members_query(date_from, date_to))
        members = tuple(BalanceCookMember(*row) for row in member_rows)
        vote_rows = await self._session.execute(self._votes_query(date_from, date_to))
        votes = tuple((row.member_id, row.position, row.value) for row in vote_rows)
        charges = [
            BalanceCookResponse(
                id=charge.cook_id,
                cook_date=charge.cook_date,
                title=charge.title,
                amount=charge.amount,
            )
            for charge in calculate_cook_charges(members, votes)
            if charge.user_id == user_id and charge.cook_id is not None
        ]
        adjustment_rows = await self._session.execute(
            select(BalanceAdjustment, User.name)
            .outerjoin(User, User.id == BalanceAdjustment.created_by_user_id)
            .where(
                BalanceAdjustment.user_id == user_id,
                BalanceAdjustment.adjustment_date.between(date_from, date_to),
            )
            .order_by(BalanceAdjustment.adjustment_date, BalanceAdjustment.created_at)
        )
        adjustments = [
            BalanceAdjustmentResponse(
                id=value.id,
                adjustment_date=value.adjustment_date,
                amount=value.amount,
                balance_before=value.balance_before,
                reason=value.reason,
                created_at=value.created_at,
                created_by_name=author_name,
            )
            for value, author_name in adjustment_rows
        ]
        return payments, charges, adjustments

    async def _load(self, date_from: date, date_to: date) -> tuple[AggregatedUserBalance, ...]:
        users_result = await self._session.execute(
            select(User.id, User.name).order_by(User.name.asc(), User.id.asc())
        )
        users = tuple(BalanceUser(row.id, row.name) for row in users_result)

        payments_result = await self._session.execute(self._payments_query(date_from, date_to))
        payments = tuple(
            PaymentTotal(row.user_id, row.payment_date, int(row.amount)) for row in payments_result
        )

        members_result = await self._session.execute(self._members_query(date_from, date_to))
        members = tuple(BalanceCookMember(*row) for row in members_result)

        votes_result = await self._session.execute(self._votes_query(date_from, date_to))
        votes = tuple((row.member_id, row.position, row.value) for row in votes_result)
        charges = calculate_cook_charges(members, votes)
        adjustments_result = await self._session.execute(
            select(
                BalanceAdjustment.user_id,
                BalanceAdjustment.adjustment_date,
                func.sum(BalanceAdjustment.amount).label("amount"),
            )
            .where(BalanceAdjustment.adjustment_date.between(date_from, date_to))
            .group_by(BalanceAdjustment.user_id, BalanceAdjustment.adjustment_date)
        )
        adjustments = tuple(
            AdjustmentTotal(row.user_id, row.adjustment_date, int(row.amount))
            for row in adjustments_result
        )
        return aggregate_balances(users, payments, charges, date_from, date_to, adjustments)

    @staticmethod
    def _payments_query(date_from: date, date_to: date) -> Select[tuple[UUID, date, int]]:
        return (
            select(
                Payment.user_id,
                Payment.payment_date,
                func.sum(Payment.sum).label("amount"),
            )
            .where(Payment.payment_date.between(date_from, date_to))
            .where(Payment.included_in_balance.is_(True))
            .group_by(Payment.user_id, Payment.payment_date)
        )

    @staticmethod
    def _members_query(date_from: date, date_to: date) -> Select:
        return (
            select(
                Cook.id,
                Cook.cook_date,
                Cook.total_price_cached,
                Cook.sale,
                CookMember.id,
                CookMember.user_id,
                CookMember.position,
                CookMember.active,
                CookMember.permanent_sale_snapshot,
                Cook.type_snapshot,
            )
            .join(CookMember, CookMember.cook_id == Cook.id)
            .where(Cook.cook_date.between(date_from, date_to))
            .order_by(Cook.cook_date, Cook.id, CookMember.position)
        )

    @staticmethod
    def _votes_query(date_from: date, date_to: date) -> Select:
        return (
            select(
                CookMemberVote.cook_member_id.label("member_id"),
                CookMemberVote.position,
                CookVoteVariant.value,
            )
            .join(CookMember, CookMember.id == CookMemberVote.cook_member_id)
            .join(Cook, Cook.id == CookMember.cook_id)
            .join(CookVoteVariant, CookVoteVariant.id == CookMemberVote.cook_vote_variant_id)
            .where(Cook.cook_date.between(date_from, date_to))
            .order_by(CookMemberVote.cook_member_id, CookMemberVote.position)
        )


__all__ = [
    "AggregatedUserBalance",
    "BalanceDataError",
    "BalanceCookMember",
    "BalanceService",
    "BalanceUser",
    "CookCharge",
    "PaymentTotal",
    "PaymentNotFoundError",
    "PaymentTypeNotFoundError",
    "UserNotFoundError",
    "aggregate_balances",
    "calculate_cook_charges",
    "legacy_week",
    "legacy_week_display",
]
