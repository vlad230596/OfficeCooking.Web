from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.contracts import BalancesQuery, CalculateSelectionResponse


def test_balances_require_explicit_dates_and_support_non_zero_filter() -> None:
    query = BalancesQuery.model_validate(
        {"dateFrom": "2023-06-05", "dateTo": "2026-08-19", "nonZeroOnly": True}
    )
    assert query.non_zero_only is True
    with pytest.raises(ValidationError):
        BalancesQuery.model_validate({"dateTo": "2026-08-19"})


def test_selection_response_exposes_full_and_positive_only_views() -> None:
    response = CalculateSelectionResponse.model_validate(
        {
            "cookIds": ["11111111-1111-4111-8111-111111111111"],
            "charges": [
                {
                    "userId": "22222222-2222-4222-8222-222222222222",
                    "userName": "Zero",
                    "charge": 0,
                },
                {
                    "userId": "33333333-3333-4333-8333-333333333333",
                    "userName": "Positive",
                    "charge": 25,
                },
            ],
            "total": 25,
            "positiveCharges": [
                {
                    "userId": "33333333-3333-4333-8333-333333333333",
                    "userName": "Positive",
                    "charge": 25,
                }
            ],
            "positiveTotal": 25,
        }
    )
    assert response.positive_total == 25
    assert [charge.charge for charge in response.positive_charges] == [25]


def test_selection_response_rejects_non_positive_legacy_view() -> None:
    payload = {
        "cookIds": ["11111111-1111-4111-8111-111111111111"],
        "charges": [
            {
                "userId": "22222222-2222-4222-8222-222222222222",
                "userName": "Zero",
                "charge": 0,
            }
        ],
        "total": 0,
        "positiveCharges": [
            {
                "userId": "22222222-2222-4222-8222-222222222222",
                "userName": "Zero",
                "charge": 0,
            }
        ],
        "positiveTotal": 0,
    }
    with pytest.raises(ValidationError, match="positive-only"):
        CalculateSelectionResponse.model_validate(payload)
