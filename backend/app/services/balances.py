"""Balance aggregation and bounded-query persistence adapter."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts import (
    BalancesResponse,
    OrderingMetadata,
    SortField,
    UserBalanceDetailResponse,
    UserBalanceResponse,
    WeekBalanceResponse,
)
from app.domain.legacy_calculation import LegacyCalculationError, ceil_to_5, float32
from app.models import Cook, CookMember, CookMemberVote, CookVoteVariant, Payment, User


class BalanceDataError(RuntimeError):
    """Stored data cannot produce a safe Legacy balance."""


class UserNotFoundError(LookupError):
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


@dataclass(slots=True)
class _MutableWeek:
    positive: int = 0
    negative: int = 0
    cooks_count: int = 0


@dataclass(frozen=True, slots=True)
class AggregatedUserBalance:
    user: BalanceUser
    positive: int
    negative: int
    cooks_count: int
    cumulative_balance: int
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


def legacy_week(value: date) -> tuple[int, int]:
    """GregorianCalendar.GetWeekOfYear(FirstDay, Monday) with date.Year."""

    january_first = value.replace(month=1, day=1)
    week = ((value.timetuple().tm_yday - 1 + january_first.weekday()) // 7) + 1
    return value.year, week


def aggregate_balances(
    users: Sequence[BalanceUser],
    payments: Iterable[PaymentTotal],
    charges: Iterable[CookCharge],
    date_from: date,
    date_to: date,
) -> tuple[AggregatedUserBalance, ...]:
    """Aggregate inclusive-range events using the Legacy week identity."""

    known_users = {user.id for user in users}
    weeks: dict[UUID, dict[tuple[int, int], _MutableWeek]] = {
        user.id: {} for user in users
    }

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

    result: list[AggregatedUserBalance] = []
    for user in users:
        cumulative = 0
        week_responses: list[WeekBalanceResponse] = []
        total_positive = total_negative = total_cooks = 0
        for (year, week), value in sorted(weeks[user.id].items()):
            weekly_delta = value.positive - value.negative
            cumulative += weekly_delta
            total_positive += value.positive
            total_negative += value.negative
            total_cooks += value.cooks_count
            week_responses.append(
                WeekBalanceResponse(
                    year=year,
                    week=week,
                    display=f"{year}#{week}",
                    positive=value.positive,
                    negative=value.negative,
                    cooks_count=value.cooks_count,
                    weekly_delta=weekly_delta,
                    cumulative_balance=cumulative,
                )
            )
        result.append(
            AggregatedUserBalance(
                user=user,
                positive=total_positive,
                negative=total_negative,
                cooks_count=total_cooks,
                cumulative_balance=cumulative,
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
                charges.append(CookCharge(member.user_id, member.cook_date, amount))
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
        return UserBalanceDetailResponse(
            user_id=item.user.id,
            user_name=item.user.name,
            date_from=date_from,
            date_to=date_to,
            weeks=list(item.weeks),
            ordering=OrderingMetadata(
                fields=[
                    SortField(field="year", direction="asc"),
                    SortField(field="week", direction="asc"),
                ]
            ),
        )

    async def _load(
        self, date_from: date, date_to: date
    ) -> tuple[AggregatedUserBalance, ...]:
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
        return aggregate_balances(users, payments, charges, date_from, date_to)

    @staticmethod
    def _payments_query(date_from: date, date_to: date) -> Select[tuple[UUID, date, int]]:
        return (
            select(
                Payment.user_id,
                Payment.payment_date,
                func.sum(Payment.sum).label("amount"),
            )
            .where(Payment.payment_date.between(date_from, date_to))
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
    "UserNotFoundError",
    "aggregate_balances",
    "calculate_cook_charges",
    "legacy_week",
]
