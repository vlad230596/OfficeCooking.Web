from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts.calculations import (
    ExpressionPreviewRequest,
    ExpressionPreviewResponse,
)
from app.api.contracts.cooks import (
    CalculateSelectionRequest,
    CalculateSelectionResponse,
    CookDetailResponse,
    CookMemberResponse,
    CookProductPriceResponse,
    CooksPageResponse,
    CooksQuery,
    CookSummaryResponse,
    CookVoteVariantResponse,
    CreateCookRequest,
    DraftCookPreviewRequest,
    DraftCookPreviewResponse,
    DraftMemberChargeResponse,
    UpdateCookRequest,
    UserChargeResponse,
)
from app.api.contracts.pagination import OrderingMetadata, SortField
from app.domain.legacy_calculation import (
    CalculationStatus,
    CookCalculation,
    MemberInput,
    ProductInput,
    calculate_cook,
    evaluate_expression,
    float32,
)
from app.models import (
    Cook,
    CookMember,
    CookMemberVote,
    CookProductPrice,
    CookTemplate,
    CookVoteVariant,
    TemplateVoteVariant,
    User,
)

CALCULATION_VERSION = 1
NEW_COOK_SALE = float32(0.6)


class CookServiceError(RuntimeError):
    code = "cook_error"
    status_code = 400

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class CookNotFoundError(CookServiceError):
    code = "cook_not_found"
    status_code = 404


class TemplateNotFoundError(CookServiceError):
    code = "template_not_found"
    status_code = 404


class DateConflictError(CookServiceError):
    code = "cook_date_conflict"
    status_code = 409


class VersionConflictError(CookServiceError):
    code = "cook_version_conflict"
    status_code = 409


class InvalidSnapshotError(CookServiceError):
    code = "invalid_cook_snapshot"
    status_code = 422


@dataclass(slots=True)
class _LoadedCook:
    cook: Cook
    variants: list[CookVoteVariant]
    members: list[CookMember]
    users: dict[UUID, User]
    votes_by_member: dict[UUID, list[CookMemberVote]]
    products: list[CookProductPrice]
    calculation: CookCalculation


class CooksService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_cooks(self, query: CooksQuery) -> CooksPageResponse:
        filters = [Cook.cook_date >= query.date_from, Cook.cook_date <= query.date_to]
        if query.template_id is not None:
            filters.append(Cook.template_id == query.template_id)
        total = int(
            await self.session.scalar(select(func.count()).select_from(Cook).where(*filters)) or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    select(Cook)
                    .where(*filters)
                    .order_by(Cook.cook_date.desc(), Cook.id.asc())
                    .offset((query.page - 1) * query.page_size)
                    .limit(query.page_size)
                )
            ).all()
        )
        items: list[CookSummaryResponse] = []
        for cook in rows:
            loaded = await self._load(cook)
            items.append(
                CookSummaryResponse(
                    id=cook.id,
                    cook_date=cook.cook_date,
                    template_id=cook.template_id,
                    type_snapshot=cook.type_snapshot,
                    member_count=len(loaded.members),
                    total_vote_weight=self._sum_vote_weight(loaded.calculation),
                    total_price=cook.total_price_cached,
                    row_version=cook.row_version,
                )
            )
        return CooksPageResponse(
            items=items,
            page=query.page,
            page_size=query.page_size,
            total_items=total,
            total_pages=math.ceil(total / query.page_size),
            ordering=OrderingMetadata(
                fields=[
                    SortField(field="cookDate", direction="desc"),
                    SortField(field="id", direction="asc"),
                ]
            ),
        )

    async def get_cook(self, cook_id: UUID) -> CookDetailResponse:
        cook = await self.session.get(Cook, cook_id)
        if cook is None:
            raise CookNotFoundError("Cook was not found.")
        return self._detail(await self._load(cook))

    async def create_cook(self, request: CreateCookRequest) -> CookDetailResponse:
        if await self._cook_id_on_date(request.cook_date) is not None:
            raise DateConflictError(
                "A cook already exists on this date.",
                details={"cookDate": request.cook_date.isoformat()},
            )
        template = await self.session.get(CookTemplate, request.template_id)
        if template is None:
            raise TemplateNotFoundError("Cook template was not found.")
        template_variants = list(
            (
                await self.session.scalars(
                    select(TemplateVoteVariant)
                    .where(TemplateVoteVariant.template_id == template.id)
                    .order_by(TemplateVoteVariant.position.asc())
                )
            ).all()
        )
        variant_positions = {variant.position for variant in template_variants}
        members = [member for member in request.members if member.vote_variant_positions]
        for member in members:
            invalid = set(member.vote_variant_positions) - variant_positions
            if invalid:
                raise InvalidSnapshotError(
                    "Member votes must reference template variant positions.",
                    details={"positions": sorted(invalid)},
                )
        users = await self._users({member.user_id for member in members})
        cook_id = uuid.uuid4()
        source_key = f"web:cooks:{cook_id}"
        variants = [
            CookVoteVariant(
                id=uuid.uuid4(),
                cook_id=cook_id,
                position=variant.position,
                name=variant.name,
                value=float32(variant.value),
            )
            for variant in template_variants
        ]
        variants_by_position = {variant.position: variant for variant in variants}
        products: list[CookProductPrice] = []
        requested_products = sorted(request.product_prices, key=lambda item: item.position)
        product_inputs = [
            ProductInput(product.product_name, product.expression)
            for product in requested_products
        ]
        member_inputs = self._create_member_inputs(members, users, variants)
        calculation = calculate_cook(
            product_inputs,
            [variant.value for variant in variants],
            member_inputs,
            NEW_COOK_SALE,
        )
        self._require_valid_calculation(calculation)
        for requested, product_input, result in zip(
            requested_products, product_inputs, calculation.products, strict=True
        ):
            products.append(
                CookProductPrice(
                    id=uuid.uuid4(),
                    cook_id=cook_id,
                    position=requested.position,
                    product_name=product_input.product_name,
                    expression=product_input.expression,
                    computed_value=result.result.value,
                    calculation_status=result.result.status.value,
                    calculation_error=result.result.error,
                    calculation_version=CALCULATION_VERSION,
                )
            )
        cook = Cook(
            id=cook_id,
            cook_date=request.cook_date,
            legacy_filename=f"web-{cook_id}.json",
            source_key=source_key,
            template_id=template.id,
            type_snapshot=template.legacy_name,
            sale=NEW_COOK_SALE,
            total_price_cached=calculation.total_price,
            calculation_version=CALCULATION_VERSION,
            row_version=1,
        )
        member_rows, vote_rows = self._create_member_rows(
            cook_id,
            members,
            variants_by_position,
            {user_id: user.permanent_sale for user_id, user in users.items()},
        )
        try:
            self.session.add_all([cook, *variants, *member_rows, *vote_rows, *products])
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DateConflictError("A cook already exists on this date.") from exc
        return await self.get_cook(cook_id)

    async def update_cook(self, cook_id: UUID, request: UpdateCookRequest) -> CookDetailResponse:
        cook = await self.session.scalar(select(Cook).where(Cook.id == cook_id).with_for_update())
        if cook is None:
            raise CookNotFoundError("Cook was not found.")
        if cook.row_version != request.expected_version:
            raise VersionConflictError(
                "Cook was changed by another request.",
                details={"currentVersion": cook.row_version},
            )
        conflicting_id = await self._cook_id_on_date(request.cook_date, exclude_id=cook_id)
        if conflicting_id is not None:
            raise DateConflictError(
                "A cook already exists on this date.",
                details={"cookId": str(conflicting_id)},
            )
        existing_variants = list(
            (
                await self.session.scalars(
                    select(CookVoteVariant).where(CookVoteVariant.cook_id == cook_id)
                )
            ).all()
        )
        if {variant.id for variant in existing_variants} != {
            variant.id for variant in request.vote_variants
        }:
            raise InvalidSnapshotError("voteVariants must be the existing historical snapshot.")
        existing_members = list(
            (
                await self.session.scalars(
                    select(CookMember).where(CookMember.cook_id == cook_id)
                )
            ).all()
        )
        existing_members_by_id = {member.id: member for member in existing_members}
        existing_member_ids = set(existing_members_by_id)
        existing_product_ids = set(
            (
                await self.session.scalars(
                    select(CookProductPrice.id).where(CookProductPrice.cook_id == cook_id)
                )
            ).all()
        )
        supplied_member_ids = {member.id for member in request.members if member.id is not None}
        supplied_product_ids = {
            product.id for product in request.product_prices if product.id is not None
        }
        if not supplied_member_ids <= existing_member_ids:
            raise InvalidSnapshotError("A member id belongs to another cook.")
        if not supplied_product_ids <= existing_product_ids:
            raise InvalidSnapshotError("A product price id belongs to another cook.")
        variants = sorted(request.vote_variants, key=lambda item: item.position)
        variant_by_id = {variant.id: variant for variant in variants}
        users = await self._users({member.user_id for member in request.members})
        permanent_sales: dict[UUID, float] = {}
        for member in request.members:
            if member.id is not None:
                existing = existing_members_by_id[member.id]
                if existing.user_id != member.user_id:
                    raise InvalidSnapshotError("A historical member cannot change its user.")
                permanent_sales[member.user_id] = existing.permanent_sale_snapshot
            else:
                permanent_sales[member.user_id] = users[member.user_id].permanent_sale
        member_inputs = [
            MemberInput(
                user_id=member.user_id,  # type: ignore[arg-type]
                active=member.active,
                vote_indexes=tuple(
                    variants.index(variant_by_id[vote_id])
                    for vote_id in member.cook_vote_variant_ids
                ),
                permanent_sale=permanent_sales[member.user_id],
            )
            for member in sorted(request.members, key=lambda item: item.position)
            if member.cook_vote_variant_ids
        ]
        products_request = sorted(request.product_prices, key=lambda item: item.position)
        product_inputs = [
            ProductInput(product.product_name, product.expression) for product in products_request
        ]
        calculation = calculate_cook(
            product_inputs,
            [variant.value for variant in variants],
            member_inputs,
            cook.sale,
        )
        self._require_valid_calculation(calculation)
        existing_variants_by_id = {variant.id: variant for variant in existing_variants}
        temporary_position = 1 + max(
            [variant.position for variant in existing_variants]
            + [variant.position for variant in variants],
            default=0,
        )
        for offset, row in enumerate(existing_variants):
            row.position = temporary_position + offset
        await self.session.flush()
        for incoming in variants:
            row = existing_variants_by_id[incoming.id]
            row.position = incoming.position
            row.name = incoming.name
            row.value = float32(incoming.value)
        await self.session.execute(delete(CookMemberVote).where(CookMemberVote.cook_id == cook_id))
        for existing_member in existing_members:
            self.session.expunge(existing_member)
        await self.session.execute(delete(CookMember).where(CookMember.cook_id == cook_id))
        await self.session.execute(
            delete(CookProductPrice).where(CookProductPrice.cook_id == cook_id)
        )
        variant_rows_by_id = {row.id: row for row in existing_variants}
        member_rows: list[CookMember] = []
        vote_rows: list[CookMemberVote] = []
        for member in sorted(request.members, key=lambda item: item.position):
            if not member.cook_vote_variant_ids:
                continue
            member_id = member.id or uuid.uuid4()
            member_rows.append(
                CookMember(
                    id=member_id,
                    cook_id=cook_id,
                    user_id=member.user_id,
                    position=member.position,
                    active=member.active,
                    permanent_sale_snapshot=permanent_sales[member.user_id],
                )
            )
            for position, variant_id in enumerate(member.cook_vote_variant_ids):
                if variant_id not in variant_rows_by_id:
                    raise InvalidSnapshotError("A vote variant belongs to another cook.")
                vote_rows.append(
                    CookMemberVote(
                        cook_id=cook_id,
                        cook_member_id=member_id,
                        cook_vote_variant_id=variant_id,
                        position=position,
                    )
                )
        products = [
            CookProductPrice(
                id=incoming.id or uuid.uuid4(),
                cook_id=cook_id,
                position=incoming.position,
                product_name=incoming.product_name,
                expression=incoming.expression,
                computed_value=result.result.value,
                calculation_status=result.result.status.value,
                calculation_error=result.result.error,
                calculation_version=CALCULATION_VERSION,
            )
            for incoming, result in zip(products_request, calculation.products, strict=True)
        ]
        cook.cook_date = request.cook_date
        cook.total_price_cached = calculation.total_price
        cook.calculation_version = CALCULATION_VERSION
        cook.row_version += 1
        try:
            self.session.add_all([*member_rows, *vote_rows, *products])
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DateConflictError("A cook already exists on this date.") from exc
        return await self.get_cook(cook_id)

    async def calculate_selection(
        self, request: CalculateSelectionRequest
    ) -> CalculateSelectionResponse:
        charges: dict[UUID, int] = {}
        names: dict[UUID, str] = {}
        for cook_id in request.cook_ids:
            cook = await self.session.get(Cook, cook_id)
            if cook is None:
                raise CookNotFoundError(
                    "A selected cook was not found.", details={"cookId": str(cook_id)}
                )
            loaded = await self._load(cook)
            if loaded.calculation.status is CalculationStatus.ERROR:
                raise InvalidSnapshotError(
                    "A selected cook cannot be calculated.",
                    details={"cookId": str(cook_id), "reason": loaded.calculation.error or ""},
                )
            for member, calculated in zip(loaded.members, loaded.calculation.members, strict=True):
                charge = calculated.charge
                if charge is None:
                    raise InvalidSnapshotError("A selected cook has no member charge.")
                charges[member.user_id] = charges.get(member.user_id, 0) + charge
                names[member.user_id] = loaded.users[member.user_id].name
        full = [
            UserChargeResponse(user_id=user_id, user_name=names[user_id], charge=charge)
            for user_id, charge in charges.items()
        ]
        positive = [item for item in full if item.charge > 0]
        return CalculateSelectionResponse(
            cook_ids=request.cook_ids,
            charges=full,
            total=sum(item.charge for item in full),
            positive_charges=positive,
            positive_total=sum(item.charge for item in positive),
        )

    async def preview_cook(self, request: DraftCookPreviewRequest) -> DraftCookPreviewResponse:
        sale = NEW_COOK_SALE
        if request.cook_id is not None:
            cook = await self.session.get(Cook, request.cook_id)
            if cook is None:
                raise CookNotFoundError("Cook was not found.")
            sale = cook.sale

        variants = sorted(request.vote_variants, key=lambda item: item.position)
        variant_index = {variant.id: index for index, variant in enumerate(variants)}
        members = sorted(request.members, key=lambda item: item.position)
        users = await self._users({member.user_id for member in members})
        permanent_sales = {user_id: user.permanent_sale for user_id, user in users.items()}
        if request.cook_id is not None:
            stored_members = list(
                (
                    await self.session.scalars(
                        select(CookMember).where(CookMember.cook_id == request.cook_id)
                    )
                ).all()
            )
            permanent_sales.update(
                {member.user_id: member.permanent_sale_snapshot for member in stored_members}
            )
        calculation = calculate_cook(
            [
                ProductInput(product.product_name, product.expression)
                for product in sorted(request.product_prices, key=lambda item: item.position)
            ],
            [float32(variant.value) for variant in variants],
            [
                MemberInput(
                    user_id=member.user_id,  # type: ignore[arg-type]
                    active=member.active,
                    vote_indexes=tuple(
                        variant_index[vote_id] for vote_id in member.cook_vote_variant_ids
                    ),
                    permanent_sale=permanent_sales[member.user_id],
                )
                for member in members
            ],
            sale,
        )
        self._require_valid_calculation(calculation)
        if calculation.total_price is None:
            raise InvalidSnapshotError("Cook preview has no total price.")
        result_members: list[DraftMemberChargeResponse] = []
        for member, calculated in zip(members, calculation.members, strict=True):
            if calculated.charge is None:
                raise InvalidSnapshotError("Cook preview has no member charge.")
            result_members.append(
                DraftMemberChargeResponse(
                    user_id=member.user_id,
                    user_name=users[member.user_id].name,
                    charge=calculated.charge,
                )
            )
        return DraftCookPreviewResponse(
            total_price=calculation.total_price,
            members=result_members,
            calculation_version=CALCULATION_VERSION,
        )

    async def _cook_id_on_date(
        self, cook_date: date, *, exclude_id: UUID | None = None
    ) -> UUID | None:
        statement = select(Cook.id).where(Cook.cook_date == cook_date)
        if exclude_id is not None:
            statement = statement.where(Cook.id != exclude_id)
        return await self.session.scalar(statement)

    async def _users(self, user_ids: set[UUID]) -> dict[UUID, User]:
        if not user_ids:
            return {}
        rows = list((await self.session.scalars(select(User).where(User.id.in_(user_ids)))).all())
        result = {row.id: row for row in rows}
        missing = user_ids - set(result)
        if missing:
            raise InvalidSnapshotError(
                "One or more users were not found.",
                details={"userIds": sorted(str(identifier) for identifier in missing)},
            )
        return result

    async def _load(self, cook: Cook) -> _LoadedCook:
        variants = list(
            (
                await self.session.scalars(
                    select(CookVoteVariant)
                    .where(CookVoteVariant.cook_id == cook.id)
                    .order_by(CookVoteVariant.position.asc())
                )
            ).all()
        )
        members = list(
            (
                await self.session.scalars(
                    select(CookMember)
                    .where(CookMember.cook_id == cook.id)
                    .order_by(CookMember.position.asc())
                )
            ).all()
        )
        users = await self._users({member.user_id for member in members})
        votes = list(
            (
                await self.session.scalars(
                    select(CookMemberVote)
                    .where(CookMemberVote.cook_id == cook.id)
                    .order_by(CookMemberVote.cook_member_id.asc(), CookMemberVote.position.asc())
                )
            ).all()
        )
        votes_by_member: dict[UUID, list[CookMemberVote]] = defaultdict(list)
        for vote in votes:
            votes_by_member[vote.cook_member_id].append(vote)
        products = list(
            (
                await self.session.scalars(
                    select(CookProductPrice)
                    .where(CookProductPrice.cook_id == cook.id)
                    .order_by(CookProductPrice.position.asc())
                )
            ).all()
        )
        variant_index = {variant.id: index for index, variant in enumerate(variants)}
        calculation = calculate_cook(
            [ProductInput(product.product_name, product.expression) for product in products],
            [variant.value for variant in variants],
            [
                MemberInput(
                    user_id=member.user_id,  # type: ignore[arg-type]
                    active=member.active,
                    vote_indexes=tuple(
                        variant_index[vote.cook_vote_variant_id]
                        for vote in votes_by_member[member.id]
                    ),
                    permanent_sale=member.permanent_sale_snapshot,
                )
                for member in members
            ],
            cook.sale,
        )
        return _LoadedCook(cook, variants, members, users, votes_by_member, products, calculation)

    def _detail(self, loaded: _LoadedCook) -> CookDetailResponse:
        calculation_by_index = {result.index: result for result in loaded.calculation.members}
        return CookDetailResponse(
            id=loaded.cook.id,
            cook_date=loaded.cook.cook_date,
            template_id=loaded.cook.template_id,
            type_snapshot=loaded.cook.type_snapshot,
            sale=loaded.cook.sale,
            total_price=loaded.cook.total_price_cached,
            calculation_version=loaded.cook.calculation_version,
            row_version=loaded.cook.row_version,
            vote_variants=[
                CookVoteVariantResponse.model_validate(variant, from_attributes=True)
                for variant in loaded.variants
            ],
            members=[
                CookMemberResponse(
                    id=member.id,
                    position=member.position,
                    user_id=member.user_id,
                    user_name=loaded.users[member.user_id].name,
                    active=member.active,
                    permanent_sale_snapshot=member.permanent_sale_snapshot,
                    cook_vote_variant_ids=[
                        vote.cook_vote_variant_id for vote in loaded.votes_by_member[member.id]
                    ],
                    vote_weight=calculation_by_index[index].vote_weight,
                    effective_weight=calculation_by_index[index].effective_weight,
                    charge=calculation_by_index[index].charge,
                )
                for index, member in enumerate(loaded.members)
            ],
            product_prices=[
                CookProductPriceResponse.model_validate(product, from_attributes=True)
                for product in loaded.products
            ],
        )

    @staticmethod
    def _sum_vote_weight(calculation: CookCalculation) -> float:
        total = 0.0
        for member in calculation.members:
            total = float32(total + member.vote_weight)
        return total

    @staticmethod
    def _require_valid_calculation(calculation: CookCalculation) -> None:
        if calculation.status is CalculationStatus.ERROR:
            raise InvalidSnapshotError(
                "Cook calculation failed.", details={"reason": calculation.error or ""}
            )

    @staticmethod
    def _create_member_inputs(members, users, variants) -> list[MemberInput]:
        index_by_position = {variant.position: index for index, variant in enumerate(variants)}
        return [
            MemberInput(
                user_id=member.user_id,  # type: ignore[arg-type]
                active=member.active,
                vote_indexes=tuple(
                    index_by_position[position] for position in member.vote_variant_positions
                ),
                permanent_sale=users[member.user_id].permanent_sale,
            )
            for member in sorted(members, key=lambda item: item.position)
        ]

    @staticmethod
    def _create_member_rows(cook_id, members, variants_by_position, permanent_sales):
        member_rows: list[CookMember] = []
        vote_rows: list[CookMemberVote] = []
        for member in sorted(members, key=lambda item: item.position):
            if not member.vote_variant_positions:
                continue
            member_id = uuid.uuid4()
            member_rows.append(
                CookMember(
                    id=member_id,
                    cook_id=cook_id,
                    user_id=member.user_id,
                    position=member.position,
                    active=member.active,
                    permanent_sale_snapshot=permanent_sales[member.user_id],
                )
            )
            for vote_position, variant_position in enumerate(member.vote_variant_positions):
                vote_rows.append(
                    CookMemberVote(
                        cook_id=cook_id,
                        cook_member_id=member_id,
                        cook_vote_variant_id=variants_by_position[variant_position].id,
                        position=vote_position,
                    )
                )
        return member_rows, vote_rows


def preview_expression(request: ExpressionPreviewRequest) -> ExpressionPreviewResponse:
    result = evaluate_expression(request.expression)
    return ExpressionPreviewResponse(
        expression=request.expression,
        status=result.status.value,
        computed_value=result.value,
        error=result.error,
        calculation_version=CALCULATION_VERSION,
    )
