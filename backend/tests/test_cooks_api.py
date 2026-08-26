from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.contracts import (
    CalculateSelectionResponse,
    CookDetailResponse,
    CooksPageResponse,
    CreateCookRequest,
    DraftCookPreviewRequest,
    DraftCookPreviewResponse,
    DraftMemberChargeResponse,
    UserChargeResponse,
)
from app.api.contracts.calculations import ExpressionPreviewRequest
from app.api.routes.cooks import get_cooks_service, router
from app.domain.legacy_calculation import (
    CalculationStatus,
    CookCalculation,
    MemberCalculation,
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
from app.services.cooks import (
    NEW_COOK_SALE,
    CooksService,
    DateConflictError,
    _LoadedCook,
    preview_expression,
)

COOK_ID = UUID("11111111-1111-4111-8111-111111111111")
TEMPLATE_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")
VARIANT_ID = UUID("44444444-4444-4444-8444-444444444444")
MEMBER_ID = UUID("55555555-5555-4555-8555-555555555555")
PRODUCT_ID = UUID("66666666-6666-4666-8666-666666666666")
SECOND_USER_ID = UUID("77777777-7777-4777-8777-777777777777")


def _detail(*, row_version: int = 1) -> CookDetailResponse:
    return CookDetailResponse.model_validate(
        {
            "id": COOK_ID,
            "cookDate": "2026-08-19",
            "templateId": TEMPLATE_ID,
            "typeSnapshot": "Шаурма",
            "sale": NEW_COOK_SALE,
            "totalPrice": 190.0,
            "calculationVersion": 1,
            "rowVersion": row_version,
            "voteVariants": [{"id": VARIANT_ID, "position": 0, "name": "1", "value": 1.0}],
            "members": [
                {
                    "id": MEMBER_ID,
                    "position": 0,
                    "userId": USER_ID,
                    "userName": "Участник",
                    "active": True,
                    "permanentSaleSnapshot": 1.0,
                    "cookVoteVariantIds": [VARIANT_ID],
                    "voteWeight": 1.0,
                    "effectiveWeight": NEW_COOK_SALE,
                    "charge": 190,
                }
            ],
            "productPrices": [
                {
                    "id": PRODUCT_ID,
                    "position": 0,
                    "productName": "Мясо",
                    "expression": "2*95",
                    "computedValue": 190.0,
                    "calculationStatus": "valid",
                    "calculationError": None,
                    "calculationVersion": 1,
                }
            ],
        }
    )


class FakeCooksService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.error: Exception | None = None

    async def list_cooks(self, query):
        self.calls.append(("list", query))
        return CooksPageResponse.model_validate(
            {
                "items": [
                    {
                        "id": COOK_ID,
                        "cookDate": "2026-08-19",
                        "templateId": TEMPLATE_ID,
                        "typeSnapshot": "Шаурма",
                        "memberCount": 1,
                        "totalVoteWeight": 1.0,
                        "totalPrice": 190.0,
                        "rowVersion": 1,
                    }
                ],
                "page": query.page,
                "pageSize": query.page_size,
                "totalItems": 1,
                "totalPages": 1,
                "ordering": {
                    "fields": [
                        {"field": "cookDate", "direction": "desc"},
                        {"field": "id", "direction": "asc"},
                    ]
                },
            }
        )

    async def get_cook(self, cook_id):
        self.calls.append(("get", cook_id))
        if self.error:
            raise self.error
        return _detail()

    async def create_cook(self, request):
        self.calls.append(("create", request))
        if self.error:
            raise self.error
        return _detail()

    async def update_cook(self, cook_id, request):
        self.calls.append(("update", (cook_id, request)))
        if self.error:
            raise self.error
        return _detail(row_version=request.expected_version + 1)

    async def calculate_selection(self, request):
        self.calls.append(("selection", request))
        charge = UserChargeResponse(user_id=USER_ID, user_name="Участник", charge=190)
        return CalculateSelectionResponse(
            cook_ids=request.cook_ids,
            charges=[charge],
            total=190,
            positive_charges=[charge],
            positive_total=190,
        )

    async def preview_cook(self, request):
        self.calls.append(("preview", request))
        return DraftCookPreviewResponse(
            total_price=190.0,
            members=[
                DraftMemberChargeResponse(
                    user_id=USER_ID,
                    user_name="Участник",
                    charge=190,
                )
            ],
            calculation_version=1,
        )


@pytest.fixture
def service() -> FakeCooksService:
    return FakeCooksService()


@pytest.fixture
def app(service: FakeCooksService) -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_cooks_service] = lambda: service
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as http_client:
        yield http_client


@pytest.mark.asyncio
async def test_list_is_server_paginated_filtered_and_has_stable_order(
    client: AsyncClient, service: FakeCooksService
) -> None:
    response = await client.get(
        "/api/v1/cooks",
        params={
            "dateFrom": "2026-01-01",
            "dateTo": "2026-12-31",
            "templateId": str(TEMPLATE_ID),
            "page": 2,
            "pageSize": 25,
        },
    )

    assert response.status_code == 200
    query = service.calls[0][1]
    assert query.template_id == TEMPLATE_ID
    assert (query.page, query.page_size) == (2, 25)
    assert response.json()["ordering"]["fields"] == [
        {"field": "cookDate", "direction": "desc"},
        {"field": "id", "direction": "asc"},
    ]

    reversed_range = await client.get(
        "/api/v1/cooks",
        params={"dateFrom": "2026-12-31", "dateTo": "2026-01-01"},
    )
    assert reversed_range.status_code == 422
    assert reversed_range.json()["error"]["code"] == "invalid_cook_snapshot"


@pytest.mark.asyncio
async def test_detail_and_expression_preview(client: AsyncClient) -> None:
    detail = await client.get(f"/api/v1/cooks/{COOK_ID}")
    preview = await client.post(
        "/api/v1/calculations/expressions/preview", json={"expression": "2*95"}
    )
    invalid = await client.post(
        "/api/v1/calculations/expressions/preview", json={"expression": "2/**95"}
    )

    assert detail.status_code == 200
    assert detail.json()["sale"] == pytest.approx(NEW_COOK_SALE)
    assert preview.json()["computedValue"] == 190.0
    assert invalid.json()["status"] == "error"
    assert invalid.json()["computedValue"] is None


@pytest.mark.asyncio
async def test_draft_preview_returns_server_side_legacy_member_charges(
    client: AsyncClient, service: FakeCooksService
) -> None:
    response = await client.post(
        "/api/v1/cooks/preview",
        json={
            "cookId": None,
            "voteVariants": [
                {"id": str(VARIANT_ID), "position": 0, "value": 1.0}
            ],
            "members": [
                {
                    "position": 0,
                    "userId": str(USER_ID),
                    "active": True,
                    "cookVoteVariantIds": [str(VARIANT_ID)],
                }
            ],
            "productPrices": [
                {"position": 0, "productName": "Мясо", "expression": "2*95"}
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "totalPrice": 190.0,
        "members": [{"userId": str(USER_ID), "userName": "Участник", "charge": 190}],
        "calculationVersion": 1,
    }
    assert service.calls[0][0] == "preview"


@pytest.mark.asyncio
async def test_create_contract_owns_sale_and_rejects_client_computed_fields(
    client: AsyncClient, service: FakeCooksService
) -> None:
    payload = {
        "cookDate": "2026-08-19",
        "templateId": str(TEMPLATE_ID),
        "members": [
            {
                "position": 0,
                "userId": str(USER_ID),
                "active": True,
                "voteVariantPositions": [0],
            }
        ],
        "productPrices": [{"position": 0, "productName": "client name", "expression": "2*95"}],
    }
    response = await client.post("/api/v1/cooks", json=payload)
    untrusted = await client.post("/api/v1/cooks", json={**payload, "sale": 0.1, "totalPrice": 1})

    assert response.status_code == 201
    request = service.calls[0][1]
    assert not hasattr(request, "sale")
    assert response.json()["sale"] == pytest.approx(NEW_COOK_SALE)
    assert untrusted.status_code == 422


@pytest.mark.asyncio
async def test_put_forwards_expected_version_and_returns_incremented_version(
    client: AsyncClient, service: FakeCooksService
) -> None:
    payload = {
        "expectedVersion": 3,
        "cookDate": "2026-08-20",
        "voteVariants": [{"id": str(VARIANT_ID), "position": 0, "name": "1", "value": 1.0}],
        "members": [
            {
                "id": str(MEMBER_ID),
                "position": 0,
                "userId": str(USER_ID),
                "active": True,
                "cookVoteVariantIds": [str(VARIANT_ID)],
            }
        ],
        "productPrices": [
            {
                "id": str(PRODUCT_ID),
                "position": 0,
                "productName": "Мясо",
                "expression": "2*95",
            }
        ],
    }

    response = await client.put(f"/api/v1/cooks/{COOK_ID}", json=payload)

    assert response.status_code == 200
    assert response.json()["rowVersion"] == 4
    _, (cook_id, request) = service.calls[0]
    assert cook_id == COOK_ID
    assert request.expected_version == 3


@pytest.mark.asyncio
async def test_date_conflict_is_409_with_structured_error(
    client: AsyncClient, service: FakeCooksService
) -> None:
    service.error = DateConflictError(
        "A cook already exists on this date.", details={"cookId": str(COOK_ID)}
    )
    response = await client.get(f"/api/v1/cooks/{COOK_ID}")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "cook_date_conflict"
    assert error["details"] == {"cookId": str(COOK_ID)}
    assert error["requestId"]


@pytest.mark.asyncio
async def test_selection_returns_full_and_positive_only_views(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/cooks/calculate-selection", json={"cookIds": [str(COOK_ID)]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["charges"] == body["positiveCharges"]
    assert body["total"] == body["positiveTotal"] == 190


def test_preview_is_pure_and_member_row_builder_omits_members_without_votes() -> None:
    assert preview_expression(ExpressionPreviewRequest(expression="1,5*2")).computed_value == 3.0
    member = SimpleNamespace(
        position=0,
        user_id=USER_ID,
        active=True,
        vote_variant_positions=[],
    )

    members, votes = CooksService._create_member_rows(COOK_ID, [member], {}, {USER_ID: 1.0})

    assert members == []
    assert votes == []


@pytest.mark.asyncio
async def test_create_flushes_snapshot_parents_before_member_votes() -> None:
    template = CookTemplate(
        id=TEMPLATE_ID,
        legacy_name="Шаурма",
        source_key="templates:shawarma",
        is_multivote=False,
    )
    variant = TemplateVoteVariant(
        id=VARIANT_ID,
        template_id=TEMPLATE_ID,
        position=0,
        name="1",
        value=1.0,
    )

    class Scalars:
        def all(self):
            return [variant]

    class Session:
        def __init__(self):
            self.events: list[object] = []

        async def scalar(self, _statement):
            return None

        async def get(self, model, _identifier):
            return template if model is CookTemplate else None

        async def scalars(self, _statement):
            return Scalars()

        def add_all(self, rows):
            self.events.append([type(row) for row in rows])

        async def flush(self):
            self.events.append("flush")

        async def commit(self):
            self.events.append("commit")

        async def rollback(self):
            self.events.append("rollback")

    session = Session()
    service = CooksService(session)  # type: ignore[arg-type]
    service._users = AsyncMock(  # type: ignore[method-assign]
        return_value={USER_ID: SimpleNamespace(permanent_sale=1.0)}
    )
    service.get_cook = AsyncMock(return_value=_detail())  # type: ignore[method-assign]
    request = CreateCookRequest.model_validate(
        {
            "cookDate": "2026-08-10",
            "templateId": TEMPLATE_ID,
            "members": [
                {
                    "position": 0,
                    "userId": USER_ID,
                    "active": False,
                    "voteVariantPositions": [0],
                }
            ],
            "productPrices": [
                {"position": 0, "productName": "Продукты", "expression": "100"}
            ],
        }
    )

    await service.create_cook(request)

    assert session.events[1] == "flush"
    assert session.events[2] == [CookMemberVote]
    assert session.events[3] == "commit"


@pytest.mark.asyncio
async def test_draft_preview_uses_legacy_discount_and_ceil_to_5() -> None:
    service = CooksService(SimpleNamespace())
    service._users = AsyncMock(  # type: ignore[method-assign]
        return_value={
            USER_ID: SimpleNamespace(name="Первый", permanent_sale=1.0),
            SECOND_USER_ID: SimpleNamespace(name="Второй", permanent_sale=1.0),
        }
    )
    request = DraftCookPreviewRequest.model_validate(
        {
            "cookId": None,
            "voteVariants": [{"id": VARIANT_ID, "position": 0, "value": 1.0}],
            "members": [
                {
                    "position": 0,
                    "userId": USER_ID,
                    "active": True,
                    "cookVoteVariantIds": [VARIANT_ID],
                },
                {
                    "position": 1,
                    "userId": SECOND_USER_ID,
                    "active": False,
                    "cookVoteVariantIds": [VARIANT_ID],
                },
            ],
            "productPrices": [{"position": 0, "productName": "Итого", "expression": "100"}],
        }
    )

    response = await service.preview_cook(request)

    assert response.total_price == 100.0
    assert [(member.user_name, member.charge) for member in response.members] == [
        ("Первый", 40),
        ("Второй", 65),
    ]


@pytest.mark.asyncio
async def test_saved_cook_uses_member_discount_snapshot_after_user_changes() -> None:
    second_member_id = UUID("88888888-8888-4888-8888-888888888888")
    cook = Cook(
        id=COOK_ID,
        cook_date="2026-08-19",
        legacy_filename="snapshot.json",
        source_key="snapshot",
        template_id=TEMPLATE_ID,
        type_snapshot="Снимок",
        sale=0.6,
        total_price_cached=100,
        calculation_version=1,
        row_version=1,
    )
    variants = [
        CookVoteVariant(id=VARIANT_ID, cook_id=COOK_ID, position=0, name="1", value=1.0)
    ]
    members = [
        CookMember(
            id=MEMBER_ID,
            cook_id=COOK_ID,
            user_id=USER_ID,
            position=0,
            active=False,
            permanent_sale_snapshot=0.5,
        ),
        CookMember(
            id=second_member_id,
            cook_id=COOK_ID,
            user_id=SECOND_USER_ID,
            position=1,
            active=False,
            permanent_sale_snapshot=1.0,
        ),
    ]
    users = [
        User(
            id=USER_ID,
            legacy_id=0,
            source_key="users:0",
            name="Первый",
            permanent_sale=1.0,
            enabled=True,
        ),
        User(
            id=SECOND_USER_ID,
            legacy_id=1,
            source_key="users:1",
            name="Второй",
            permanent_sale=0.1,
            enabled=True,
        ),
    ]
    votes = [
        CookMemberVote(
            cook_id=COOK_ID,
            cook_member_id=MEMBER_ID,
            cook_vote_variant_id=VARIANT_ID,
            position=0,
        ),
        CookMemberVote(
            cook_id=COOK_ID,
            cook_member_id=second_member_id,
            cook_vote_variant_id=VARIANT_ID,
            position=0,
        ),
    ]
    products = [
        CookProductPrice(
            id=PRODUCT_ID,
            cook_id=COOK_ID,
            position=0,
            product_name="Итого",
            expression="100",
            computed_value=100,
            calculation_status="valid",
            calculation_error=None,
            calculation_version=1,
        )
    ]

    class Scalars:
        def __init__(self, values):
            self.values = values

        def all(self):
            return self.values

    class Session:
        def __init__(self):
            self.results = iter([variants, members, users, votes, products])

        async def scalars(self, _statement):
            return Scalars(next(self.results))

    loaded = await CooksService(Session())._load(cook)  # type: ignore[arg-type]

    assert [item.effective_weight for item in loaded.calculation.members] == [0.5, 1.0]
    assert [item.charge for item in loaded.calculation.members] == [35, 70]


@pytest.mark.asyncio
async def test_selection_service_keeps_nonpositive_charges_only_out_of_legacy_view() -> None:
    second_user_id = UUID("77777777-7777-4777-8777-777777777777")
    first_cook = Cook(
        id=COOK_ID,
        cook_date="2026-08-19",
        legacy_filename="first.json",
        source_key="first",
        template_id=TEMPLATE_ID,
        type_snapshot="first",
        sale=NEW_COOK_SALE,
        total_price_cached=-5.0,
        calculation_version=1,
        row_version=1,
    )
    second_cook_id = UUID("88888888-8888-4888-8888-888888888888")
    second_cook = Cook(
        id=second_cook_id,
        cook_date="2026-08-20",
        legacy_filename="second.json",
        source_key="second",
        template_id=TEMPLATE_ID,
        type_snapshot="second",
        sale=NEW_COOK_SALE,
        total_price_cached=10.0,
        calculation_version=1,
        row_version=1,
    )
    first_member = CookMember(
        id=MEMBER_ID,
        cook_id=COOK_ID,
        user_id=USER_ID,
        position=0,
        active=True,
        permanent_sale_snapshot=1.0,
    )
    second_member = CookMember(
        id=UUID("99999999-9999-4999-8999-999999999999"),
        cook_id=second_cook_id,
        user_id=second_user_id,
        position=0,
        active=True,
        permanent_sale_snapshot=1.0,
    )
    users = {
        USER_ID: User(
            id=USER_ID,
            legacy_id=0,
            source_key="users:0",
            name="Negative",
            permanent_sale=1.0,
            enabled=True,
        ),
        second_user_id: User(
            id=second_user_id,
            legacy_id=1,
            source_key="users:1",
            name="Positive",
            permanent_sale=1.0,
            enabled=True,
        ),
    }

    def loaded(cook, member, charge):
        calculation = CookCalculation(
            status=CalculationStatus.VALID,
            products=(),
            total_price=float(charge),
            members=(MemberCalculation(0, member.user_id, 1.0, 1.0, charge),),
            total_effective_weight=1.0,
            total_rounded_charges=charge,
        )
        return _LoadedCook(cook, [], [member], users, {}, [], calculation)

    loaded_by_id = {
        COOK_ID: loaded(first_cook, first_member, -5),
        second_cook_id: loaded(second_cook, second_member, 10),
    }

    class Session:
        async def get(self, _model, identifier):
            item = loaded_by_id.get(identifier)
            return item.cook if item else None

    service = CooksService(Session())  # type: ignore[arg-type]

    async def load(cook):
        return loaded_by_id[cook.id]

    service._load = load  # type: ignore[method-assign]
    response = await service.calculate_selection(
        SimpleNamespace(cook_ids=[COOK_ID, second_cook_id])
    )

    assert [charge.charge for charge in response.charges] == [-5, 10]
    assert [charge.charge for charge in response.positive_charges] == [10]
    assert response.total == 5
    assert response.positive_total == 10
