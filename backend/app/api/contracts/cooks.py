from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import Field, model_validator

from .base import ApiModel, IsoDate
from .calculations import CalculationStatus
from .pagination import OrderingMetadata, Page


class _Positioned(Protocol):
    position: int


def _ensure_unique_positions(items: list[_Positioned], collection_name: str) -> None:
    positions = [item.position for item in items]
    if len(positions) != len(set(positions)):
        raise ValueError(f"{collection_name} positions must be unique")


class CooksQuery(ApiModel):
    date_from: IsoDate
    date_to: IsoDate
    template_id: UUID | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def validate_date_range(self) -> CooksQuery:
        if self.date_from > self.date_to:
            raise ValueError("dateFrom must be on or before dateTo")
        return self


class CreateCookMemberRequest(ApiModel):
    position: int = Field(ge=0)
    user_id: UUID
    active: bool
    vote_variant_positions: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_votes(self) -> CreateCookMemberRequest:
        if any(position < 0 for position in self.vote_variant_positions):
            raise ValueError("voteVariantPositions cannot contain negative positions")
        if len(self.vote_variant_positions) != len(set(self.vote_variant_positions)):
            raise ValueError("voteVariantPositions must be unique")
        return self


class CreateCookProductPriceRequest(ApiModel):
    position: int = Field(ge=0)
    product_name: str | None = None
    expression: str | None = Field(default=None, max_length=4096)


class CreateCookRequest(ApiModel):
    cook_date: IsoDate
    template_id: UUID
    members: list[CreateCookMemberRequest]
    product_prices: list[CreateCookProductPriceRequest]

    @model_validator(mode="after")
    def validate_collections(self) -> CreateCookRequest:
        _ensure_unique_positions(self.members, "member")
        _ensure_unique_positions(self.product_prices, "product price")
        user_ids = [member.user_id for member in self.members]
        if len(user_ids) != len(set(user_ids)):
            raise ValueError("members must contain unique userId values")
        return self


class UpdateCookVoteVariantRequest(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    name: str = Field(min_length=1)
    value: float


class UpdateCookMemberRequest(ApiModel):
    id: UUID | None = None
    position: int = Field(ge=0)
    user_id: UUID
    active: bool
    cook_vote_variant_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_votes(self) -> UpdateCookMemberRequest:
        if len(self.cook_vote_variant_ids) != len(set(self.cook_vote_variant_ids)):
            raise ValueError("cookVoteVariantIds must be unique")
        return self


class UpdateCookProductPriceRequest(ApiModel):
    id: UUID | None = None
    position: int = Field(ge=0)
    product_name: str | None = None
    expression: str | None = Field(default=None, max_length=4096)


class UpdateCookRequest(ApiModel):
    expected_version: int = Field(ge=1)
    cook_date: IsoDate
    vote_variants: list[UpdateCookVoteVariantRequest]
    members: list[UpdateCookMemberRequest]
    product_prices: list[UpdateCookProductPriceRequest]

    @model_validator(mode="after")
    def validate_snapshot(self) -> UpdateCookRequest:
        _ensure_unique_positions(self.vote_variants, "vote variant")
        _ensure_unique_positions(self.members, "member")
        _ensure_unique_positions(self.product_prices, "product price")
        variant_ids = {variant.id for variant in self.vote_variants}
        member_ids = [member.id for member in self.members if member.id is not None]
        user_ids = [member.user_id for member in self.members]
        product_ids = [product.id for product in self.product_prices if product.id is not None]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("members must contain unique id values")
        if len(user_ids) != len(set(user_ids)):
            raise ValueError("members must contain unique userId values")
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("productPrices must contain unique id values")
        if any(
            vote_id not in variant_ids
            for member in self.members
            for vote_id in member.cook_vote_variant_ids
        ):
            raise ValueError("member votes must reference a vote variant in this snapshot")
        return self


class DraftCookVoteVariantRequest(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    value: float


class DraftCookMemberRequest(ApiModel):
    position: int = Field(ge=0)
    user_id: UUID
    active: bool
    cook_vote_variant_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_votes(self) -> DraftCookMemberRequest:
        if len(self.cook_vote_variant_ids) != len(set(self.cook_vote_variant_ids)):
            raise ValueError("cookVoteVariantIds must be unique")
        return self


class DraftCookProductPriceRequest(ApiModel):
    position: int = Field(ge=0)
    product_name: str | None = None
    expression: str | None = Field(default=None, max_length=4096)


class DraftCookPreviewRequest(ApiModel):
    cook_id: UUID | None = None
    vote_variants: list[DraftCookVoteVariantRequest] = Field(min_length=1)
    members: list[DraftCookMemberRequest] = Field(min_length=1)
    product_prices: list[DraftCookProductPriceRequest]

    @model_validator(mode="after")
    def validate_snapshot(self) -> DraftCookPreviewRequest:
        _ensure_unique_positions(self.vote_variants, "vote variant")
        _ensure_unique_positions(self.members, "member")
        _ensure_unique_positions(self.product_prices, "product price")
        variant_ids = {variant.id for variant in self.vote_variants}
        user_ids = [member.user_id for member in self.members]
        if len(user_ids) != len(set(user_ids)):
            raise ValueError("members must contain unique userId values")
        if any(
            vote_id not in variant_ids
            for member in self.members
            for vote_id in member.cook_vote_variant_ids
        ):
            raise ValueError("member votes must reference a draft vote variant")
        return self


class CookVoteVariantResponse(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    name: str
    value: float


class CookMemberResponse(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    user_id: UUID
    user_name: str
    active: bool
    permanent_sale_snapshot: float
    cook_vote_variant_ids: list[UUID]
    vote_weight: float
    effective_weight: float
    charge: int | None


class CookProductPriceResponse(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    product_name: str | None
    expression: str | None
    computed_value: float | None
    calculation_status: CalculationStatus
    calculation_error: str | None
    calculation_version: int = Field(ge=1)


class CookSummaryResponse(ApiModel):
    id: UUID
    cook_date: IsoDate
    template_id: UUID | None
    type_snapshot: str
    member_count: int = Field(ge=0)
    total_vote_weight: float
    total_price: float | None
    row_version: int = Field(ge=1)


class CooksPageResponse(Page[CookSummaryResponse]):
    ordering: OrderingMetadata

    @model_validator(mode="after")
    def validate_stable_cook_order(self) -> CooksPageResponse:
        order = [(item.field, item.direction) for item in self.ordering.fields]
        if order != [("cookDate", "desc"), ("id", "asc")]:
            raise ValueError("cook ordering must be cookDate desc, id asc")
        return self


class CookDetailResponse(ApiModel):
    id: UUID
    cook_date: IsoDate
    template_id: UUID | None
    type_snapshot: str
    sale: float
    total_price: float | None
    calculation_version: int = Field(ge=1)
    row_version: int = Field(ge=1)
    vote_variants: list[CookVoteVariantResponse]
    members: list[CookMemberResponse]
    product_prices: list[CookProductPriceResponse]


class CalculateSelectionRequest(ApiModel):
    cook_ids: list[UUID] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> CalculateSelectionRequest:
        if len(self.cook_ids) != len(set(self.cook_ids)):
            raise ValueError("cookIds must be unique")
        return self


class UserChargeResponse(ApiModel):
    user_id: UUID
    user_name: str
    charge: int


class DraftMemberChargeResponse(ApiModel):
    user_id: UUID
    user_name: str
    charge: int


class DraftCookPreviewResponse(ApiModel):
    total_price: float
    members: list[DraftMemberChargeResponse]
    calculation_version: int = Field(ge=1)


class CalculateSelectionResponse(ApiModel):
    cook_ids: list[UUID]
    charges: list[UserChargeResponse]
    total: int
    positive_charges: list[UserChargeResponse]
    positive_total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_totals_and_positive_view(self) -> CalculateSelectionResponse:
        if len(self.cook_ids) != len(set(self.cook_ids)):
            raise ValueError("cookIds must be unique")
        charge_ids = [item.user_id for item in self.charges]
        if len(charge_ids) != len(set(charge_ids)):
            raise ValueError("charges must contain unique userId values")
        if self.total != sum(item.charge for item in self.charges):
            raise ValueError("total must equal the sum of charges")
        expected_positive = [item for item in self.charges if item.charge > 0]
        actual_positive = [(item.user_id, item.charge) for item in self.positive_charges]
        if actual_positive != [(item.user_id, item.charge) for item in expected_positive]:
            raise ValueError("positiveCharges must be the positive-only charges view")
        if self.positive_total != sum(item.charge for item in self.positive_charges):
            raise ValueError("positiveTotal must equal the sum of positiveCharges")
        return self
