from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.contracts import (
    BalancesResponse,
    OrderingMetadata,
    SortField,
    UserBalanceDetailResponse,
)
from app.api.routes.balances import get_balance_service, router
from app.services.balances import (
    BalanceService,
    UserNotFoundError,
    legacy_week,
)


def _id(legacy_id: int) -> UUID:
    return UUID(int=legacy_id + 1)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2023, 1, 1), (2023, 1)),
        (date(2023, 1, 2), (2023, 2)),
        (date(2012, 12, 31), (2012, 54)),
        (date(2024, 1, 1), (2024, 1)),
    ],
)
def test_legacy_week_matches_gregorian_first_day_monday(
    value: date, expected: tuple[int, int]
) -> None:
    assert legacy_week(value) == expected


def test_balance_query_uses_member_discount_snapshot_not_current_user_value() -> None:
    sql = str(BalanceService._members_query(date(2026, 1, 1), date(2026, 1, 31)))
    assert "cook_members.permanent_sale_snapshot" in sql
    assert "users.permanent_sale" not in sql


@pytest.mark.asyncio
async def test_service_uses_a_bounded_four_query_set() -> None:
    user = SimpleNamespace(id=_id(0), name="One")
    results = [[user], [], [], []]

    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, _statement: object) -> list[object]:
            result = results[self.calls]
            self.calls += 1
            return result

    session = FakeSession()
    response = await BalanceService(session).list_balances(  # type: ignore[arg-type]
        date(2023, 6, 5), date(2023, 6, 5)
    )
    assert session.calls == 4
    assert response.items[0].cumulative_balance == 0


class FakeBalanceService:
    async def list_balances(
        self, date_from: date, date_to: date, *, non_zero_only: bool = False
    ) -> BalancesResponse:
        items = []
        return BalancesResponse(
            date_from=date_from,
            date_to=date_to,
            items=items,
            ordering=OrderingMetadata(
                fields=[SortField(field="userName", direction="asc")]
            ),
        )

    async def get_user_balance(
        self, user_id: UUID, date_from: date, date_to: date
    ) -> UserBalanceDetailResponse:
        raise UserNotFoundError(str(user_id))


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_balance_service] = FakeBalanceService
    return TestClient(app)


def test_router_accepts_camel_case_query_and_inclusive_single_day(client: TestClient) -> None:
    response = client.get(
        "/api/v1/balances",
        params={"dateFrom": "2023-06-05", "dateTo": "2023-06-05", "nonZeroOnly": "true"},
    )
    assert response.status_code == 200
    assert response.json()["dateFrom"] == "2023-06-05"


def test_user_not_found_uses_error_envelope(client: TestClient) -> None:
    user_id = _id(46)
    response = client.get(
        f"/api/v1/balances/users/{user_id}",
        params={"dateFrom": "2023-06-05", "dateTo": "2023-06-05"},
        headers={"x-request-id": "balance-test"},
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "user_not_found",
            "message": "User was not found.",
            "fieldErrors": [],
            "details": {"userId": str(user_id)},
            "requestId": "balance-test",
        }
    }


def test_router_rejects_reversed_range(client: TestClient) -> None:
    response = client.get(
        "/api/v1/balances",
        params={"dateFrom": "2023-06-06", "dateTo": "2023-06-05"},
    )
    assert response.status_code == 422
