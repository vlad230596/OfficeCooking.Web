from __future__ import annotations

from uuid import UUID

from pydantic import Field, model_validator

from .base import ApiModel, IsoDate
from .pagination import OrderingMetadata


class DateRangeQuery(ApiModel):
    date_from: IsoDate
    date_to: IsoDate

    @model_validator(mode="after")
    def validate_date_range(self) -> DateRangeQuery:
        if self.date_from > self.date_to:
            raise ValueError("dateFrom must be on or before dateTo")
        return self


class BalancesQuery(DateRangeQuery):
    non_zero_only: bool = False


class UserBalanceResponse(ApiModel):
    user_id: UUID
    user_name: str
    positive: int
    negative: int = Field(ge=0)
    cooks_count: int = Field(ge=0)
    cumulative_balance: int


class BalancesResponse(ApiModel):
    date_from: IsoDate
    date_to: IsoDate
    items: list[UserBalanceResponse]
    ordering: OrderingMetadata


class BalancePaymentResponse(ApiModel):
    id: UUID
    payment_date: IsoDate
    amount: int
    payment_type_name: str
    comment: str
    source: str


class BalancePaymentTypeResponse(ApiModel):
    id: UUID
    name: str


class CreateBalancePaymentRequest(ApiModel):
    payment_date: IsoDate
    amount: int = Field(gt=0)
    payment_type_id: UUID
    comment: str = Field(default="", max_length=1000)


class BalanceCookResponse(ApiModel):
    id: UUID
    cook_date: IsoDate
    title: str
    amount: int = Field(ge=0)


class WeekBalanceResponse(ApiModel):
    year: int = Field(ge=1)
    week: int = Field(ge=1, le=54)
    display: str = Field(min_length=3)
    positive: int
    negative: int = Field(ge=0)
    cooks_count: int = Field(ge=0)
    weekly_delta: int
    cumulative_balance: int
    payments: list[BalancePaymentResponse] = Field(default_factory=list)
    cooks: list[BalanceCookResponse] = Field(default_factory=list)


class UserBalanceDetailResponse(ApiModel):
    user_id: UUID
    user_name: str
    date_from: IsoDate
    date_to: IsoDate
    weeks: list[WeekBalanceResponse]
    payment_types: list[BalancePaymentTypeResponse] = Field(default_factory=list)
    ordering: OrderingMetadata
