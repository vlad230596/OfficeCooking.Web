from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .base import ApiModel, IsoDate


class RepaymentInput(ApiModel):
    id: UUID | None = None
    amount: int = Field(gt=0, le=2147483647, strict=True)
    repayment_date: IsoDate


class PurchaseInput(ApiModel):
    id: UUID | None = None
    user_id: UUID
    amount: int = Field(gt=0, le=2147483647, strict=True)
    description: str = Field(default="", max_length=1000)
    mode: Literal["offset", "separate"]
    repayments: list[RepaymentInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_repayments(self) -> "PurchaseInput":
        if sum(item.amount for item in self.repayments) > self.amount:
            raise ValueError("repayments cannot exceed the purchase amount")
        return self


class ReplaceSettlementsRequest(ApiModel):
    expected_version: int = Field(ge=1)
    purchases: list[PurchaseInput] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_ids(self) -> "ReplaceSettlementsRequest":
        for values in (
            [p.id for p in self.purchases if p.id],
            [r.id for p in self.purchases for r in p.repayments if r.id],
        ):
            if len(values) != len(set(values)):
                raise ValueError("purchase and repayment IDs must be unique")
        return self


class RepaymentResponse(ApiModel):
    id: UUID
    amount: int
    repayment_date: IsoDate


class PurchaseResponse(ApiModel):
    id: UUID
    user_id: UUID
    user_name: str
    amount: int
    description: str
    mode: Literal["offset", "separate"]
    repayments: list[RepaymentResponse]


class SettlementsResponse(ApiModel):
    cook_id: UUID
    row_version: int
    purchases: list[PurchaseResponse]


class SettlementEventResponse(ApiModel):
    id: UUID
    cook_id: UUID
    event_date: IsoDate
    kind: Literal["purchase", "reimbursement"]
    amount: int
    description: str
    mode: Literal["offset", "separate"]
    separate_owed: int | None = Field(default=None, ge=0)
