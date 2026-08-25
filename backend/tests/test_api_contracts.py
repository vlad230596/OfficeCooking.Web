from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.contracts import (
    CalculateSelectionRequest,
    CalculationStatus,
    CooksPageResponse,
    CooksQuery,
    CreateCookRequest,
    ErrorEnvelope,
    ExpressionPreviewResponse,
    PageQuery,
    UpdateCookRequest,
)

COOK_ID = "11111111-1111-4111-8111-111111111111"
TEMPLATE_ID = "22222222-2222-4222-8222-222222222222"
USER_ID = "33333333-3333-4333-8333-333333333333"
VARIANT_ID = "44444444-4444-4444-8444-444444444444"
MEMBER_ID = "55555555-5555-4555-8555-555555555555"
PRODUCT_ID = "66666666-6666-4666-8666-666666666666"


def _create_payload() -> dict:
    return {
        "cookDate": "2026-08-19",
        "templateId": TEMPLATE_ID,
        "members": [
            {
                "position": 0,
                "userId": USER_ID,
                "active": True,
                "voteVariantPositions": [0],
            }
        ],
        "productPrices": [{"position": 0, "productName": "Мясо", "expression": "2*95"}],
    }


def _update_payload() -> dict:
    return {
        "expectedVersion": 3,
        "cookDate": "2026-08-19",
        "voteVariants": [{"id": VARIANT_ID, "position": 0, "name": "Обычная", "value": 1.0}],
        "members": [
            {
                "id": MEMBER_ID,
                "position": 0,
                "userId": USER_ID,
                "active": True,
                "cookVoteVariantIds": [VARIANT_ID],
            }
        ],
        "productPrices": [
            {
                "id": PRODUCT_ID,
                "position": 0,
                "productName": "Мясо",
                "expression": "2*95",
            }
        ],
    }


def test_contracts_serialize_with_public_camel_case_names_and_iso_dates() -> None:
    request = CreateCookRequest.model_validate(_create_payload())
    assert request.cook_date == date(2026, 8, 19)
    dumped = request.model_dump(mode="json")
    assert dumped["cookDate"] == "2026-08-19"
    assert dumped["members"][0]["voteVariantPositions"] == [0]
    assert "cook_date" not in dumped


def test_mutation_json_schema_is_ready_for_openapi_and_excludes_server_fields() -> None:
    create_properties = CreateCookRequest.model_json_schema(by_alias=True)["properties"]
    assert {"cookDate", "templateId", "members", "productPrices"} == set(create_properties)
    assert {"sale", "computedValue", "totalPrice", "charges"}.isdisjoint(create_properties)
    update_properties = UpdateCookRequest.model_json_schema(by_alias=True)["properties"]
    assert "expectedVersion" in update_properties
    assert "rowVersion" not in update_properties


@pytest.mark.parametrize(
    "invalid_date",
    ["19.08.2026", "2026-8-19", "2026-02-30", "2026-08-19T00:00:00Z"],
)
def test_api_dates_are_strict_iso_calendar_dates(invalid_date: str) -> None:
    payload = _create_payload()
    payload["cookDate"] = invalid_date
    with pytest.raises(ValidationError):
        CreateCookRequest.model_validate(payload)


def test_query_requires_an_inclusive_non_reversed_range() -> None:
    query = CooksQuery.model_validate(
        {"dateFrom": "2026-08-01", "dateTo": "2026-08-19", "pageSize": 100}
    )
    assert query.page == 1
    with pytest.raises(ValidationError, match="dateFrom"):
        CooksQuery.model_validate({"dateFrom": "2026-08-20", "dateTo": "2026-08-19"})


def test_page_size_is_bounded_at_100() -> None:
    assert PageQuery.model_validate({"pageSize": 100}).page_size == 100
    with pytest.raises(ValidationError):
        PageQuery.model_validate({"pageSize": 101})


def test_create_rejects_sale_and_all_client_computed_fields() -> None:
    forbidden = {
        "sale": 0.2,
        "computedValue": 190.0,
        "totalPrice": 190.0,
        "totalPriceCached": 190.0,
        "charges": [],
    }
    for field, value in forbidden.items():
        payload = _create_payload()
        payload[field] = value
        with pytest.raises(ValidationError, match=field):
            CreateCookRequest.model_validate(payload)


def test_create_rejects_computed_product_value() -> None:
    payload = _create_payload()
    payload["productPrices"][0]["computedValue"] = 190.0
    with pytest.raises(ValidationError, match="computedValue"):
        CreateCookRequest.model_validate(payload)


def test_update_requires_version_and_does_not_accept_template_or_sale() -> None:
    assert UpdateCookRequest.model_validate(_update_payload()).expected_version == 3
    for field, value in (("templateId", TEMPLATE_ID), ("sale", 0.6)):
        payload = _update_payload()
        payload[field] = value
        with pytest.raises(ValidationError, match=field):
            UpdateCookRequest.model_validate(payload)
    payload = _update_payload()
    del payload["expectedVersion"]
    with pytest.raises(ValidationError, match="expectedVersion"):
        UpdateCookRequest.model_validate(payload)


def test_update_votes_must_reference_the_same_full_snapshot() -> None:
    payload = _update_payload()
    payload["members"][0]["cookVoteVariantIds"] = [COOK_ID]
    with pytest.raises(ValidationError, match="snapshot"):
        UpdateCookRequest.model_validate(payload)


def test_mutation_collections_require_unique_positions_and_user_ids() -> None:
    payload = _create_payload()
    payload["productPrices"].append({"position": 0, "productName": "Дубликат", "expression": "1"})
    with pytest.raises(ValidationError, match="positions"):
        CreateCookRequest.model_validate(payload)

    payload = _create_payload()
    payload["members"].append(
        {
            "position": 1,
            "userId": USER_ID,
            "active": False,
            "voteVariantPositions": [0],
        }
    )
    with pytest.raises(ValidationError, match="unique userId"):
        CreateCookRequest.model_validate(payload)


def test_selection_accepts_at_most_500_unique_cook_ids() -> None:
    ids = [UUID(int=index + 1) for index in range(500)]
    assert len(CalculateSelectionRequest(cook_ids=ids).cook_ids) == 500
    with pytest.raises(ValidationError):
        CalculateSelectionRequest(cook_ids=[*ids, UUID(int=501)])
    with pytest.raises(ValidationError, match="unique"):
        CalculateSelectionRequest(cook_ids=[ids[0], ids[0]])


def test_page_has_explicit_stable_ordering_metadata() -> None:
    response = CooksPageResponse.model_validate(
        {
            "items": [],
            "page": 1,
            "pageSize": 50,
            "totalItems": 0,
            "totalPages": 0,
            "ordering": {
                "fields": [
                    {"field": "cookDate", "direction": "desc"},
                    {"field": "id", "direction": "asc"},
                ]
            },
        }
    )
    assert [(item.field, item.direction) for item in response.ordering.fields] == [
        ("cookDate", "desc"),
        ("id", "asc"),
    ]
    with pytest.raises(ValidationError, match="totalPages"):
        CooksPageResponse.model_validate(
            {
                "items": [],
                "page": 1,
                "pageSize": 50,
                "totalItems": 1,
                "totalPages": 0,
                "ordering": {"fields": [{"field": "id", "direction": "asc"}]},
            }
        )


def test_expression_preview_enforces_status_value_error_consistency() -> None:
    valid = ExpressionPreviewResponse(
        expression="2*95",
        status=CalculationStatus.VALID,
        computed_value=190.0,
        error=None,
        calculation_version=1,
    )
    assert valid.model_dump(mode="json")["computedValue"] == 190.0
    with pytest.raises(ValidationError):
        ExpressionPreviewResponse(
            expression="1/0",
            status=CalculationStatus.ERROR,
            computed_value=0.0,
            error="division by zero",
            calculation_version=1,
        )


def test_error_envelope_has_stable_shape() -> None:
    error = ErrorEnvelope.model_validate(
        {
            "error": {
                "code": "row_version_conflict",
                "message": "The cook was changed by another client.",
                "fieldErrors": [],
                "details": {"actualRowVersion": 4},
                "requestId": "req-123",
            }
        }
    )
    assert error.model_dump(mode="json") == {
        "error": {
            "code": "row_version_conflict",
            "message": "The cook was changed by another client.",
            "fieldErrors": [],
            "details": {"actualRowVersion": 4},
            "requestId": "req-123",
        }
    }
