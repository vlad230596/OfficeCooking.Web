from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.contracts.settlements import ReplaceSettlementsRequest
from app.api.routes.balances import router as balances_router
from app.api.routes.settlements import router as settlements_router
from app.models import Base, Cook, CookMember, CookMemberVote, CookVoteVariant, User
from app.services.balances import BalanceService
from app.services.cooks import CooksService, VersionConflictError
from app.services.settlements import get_settlements, replace_settlements


@pytest.mark.asyncio
async def test_purchases_and_dated_partial_repayments_affect_balances_once():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(
                conn,
                tables=[
                    table
                    for name, table in Base.metadata.tables.items()
                    if name not in {"template_preparations", "cook_preparations"}
                ],
            )
        )
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        user_id, cook_id = uuid4(), uuid4()
        session.add(
            User(
                id=user_id,
                legacy_id=1,
                source_key="synthetic-user",
                name="Synthetic",
                permanent_sale=1,
                enabled=True,
            )
        )
        session.add(
            Cook(
                id=cook_id,
                cook_date=date(2026, 1, 5),
                legacy_filename="synthetic",
                source_key="synthetic-cook",
                type_snapshot="Test",
                sale=1,
                total_price_cached=500,
                calculation_version=1,
                row_version=1,
            )
        )
        await session.commit()
        request = ReplaceSettlementsRequest(
            expected_version=1,
            purchases=[
                {
                    "userId": user_id,
                    "amount": 500,
                    "mode": "separate",
                    "repayments": [{"amount": 200, "repaymentDate": "2026-01-12"}],
                }
            ],
        )
        result = await replace_settlements(session, cook_id, request)
        assert result.row_version == 2
        assert result.purchases[0].user_name == "Synthetic"
        with pytest.raises(VersionConflictError):
            await replace_settlements(session, cook_id, request)
        balance = await BalanceService(session).get_user_balance(
            user_id, date(2026, 1, 1), date(2026, 1, 31)
        )
        assert [w.weekly_delta for w in balance.weeks] == [500, -200]
        assert balance.weeks[-1].cumulative_balance == 300
        assert balance.weeks[0].purchases_total == 500
        assert balance.weeks[1].reimbursements_total == 200
        assert balance.weeks[0].positive == 0  # purchases are not received payments
        later = await BalanceService(session).get_user_balance(
            user_id, date(2026, 1, 12), date(2026, 1, 12)
        )
        assert later.weeks[0].weekly_delta == -200  # original cook outside date range
        replacement = ReplaceSettlementsRequest(
            expected_version=2, purchases=[result.purchases[0].model_dump(exclude={"user_name"})]
        )
        same = await replace_settlements(session, cook_id, replacement)
        assert same.purchases == result.purchases
        assert (await session.get(Cook, cook_id)).total_price_cached == 500
        await replace_settlements(
            session, cook_id, ReplaceSettlementsRequest(expected_version=3, purchases=[])
        )
        assert (await get_settlements(session, cook_id)).purchases == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_balance_api_reports_separate_debt_as_of_cutoff_even_when_balance_is_negative():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name not in {"template_preparations", "cook_preparations"}
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id, cook_id, member_id, variant_id, other_cook_id = (uuid4() for _ in range(5))
    async with session_factory() as session:
        session.add(User(id=user_id, legacy_id=1, source_key="buyer", name="Buyer", enabled=True))
        session.add(
            Cook(
                id=cook_id,
                cook_date=date(2026, 1, 5),
                legacy_filename="synthetic",
                source_key="synthetic-cook",
                type_snapshot="Test",
                sale=1,
                total_price_cached=600,
            )
        )
        await session.flush()
        session.add(
            CookMember(
                id=member_id,
                cook_id=cook_id,
                user_id=user_id,
                position=0,
                active=True,
                permanent_sale_snapshot=1,
            )
        )
        session.add(
            CookVoteVariant(id=variant_id, cook_id=cook_id, position=0, name="Portion", value=1)
        )
        await session.flush()
        session.add(
            CookMemberVote(
                cook_id=cook_id,
                cook_member_id=member_id,
                cook_vote_variant_id=variant_id,
                position=0,
            )
        )
        session.add(
            Cook(
                id=other_cook_id,
                cook_date=date(2026, 2, 5),
                legacy_filename="other-synthetic",
                source_key="other-synthetic-cook",
                type_snapshot="Other test",
                sale=1,
                total_price_cached=0,
            )
        )
        await session.commit()

    app = FastAPI()
    app.state.session_factory = session_factory
    app.include_router(balances_router)
    app.include_router(settlements_router)
    path = f"/api/v1/balances/users/{user_id}"
    settlements_path = f"/api/v1/cooks/{cook_id}/settlements"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        purchase_input = {
            "userId": str(user_id),
            "amount": 500,
            "mode": "separate",
            "repayments": [
                {"amount": 200, "repaymentDate": "2026-01-12"},
                {"amount": 300, "repaymentDate": "2026-01-19"},
            ],
        }
        payload = {
            "expectedVersion": 1,
            "purchases": [purchase_input, {"userId": str(user_id), "amount": 50, "mode": "offset"}],
        }
        saved = await client.put(settlements_path, json=payload)
        assert saved.status_code == 200
        assert saved.json()["rowVersion"] == 2
        assert saved.json()["purchases"][0]["userName"] == "Buyer"
        conflict = await client.put(settlements_path, json={"expectedVersion": 1, "purchases": []})
        assert conflict.status_code == 409
        persisted = await client.get(settlements_path)
        assert persisted.status_code == 200
        assert persisted.json() == saved.json()

        other_path = f"/api/v1/cooks/{other_cook_id}/settlements"
        [separate, _] = saved.json()["purchases"]
        invalid_purchases = [({**purchase_input, "id": separate["id"]}, "Purchase does not belong")]
        for repayment_id in (separate["repayments"][0]["id"], str(uuid4())):
            repayment = {**purchase_input["repayments"][0], "id": repayment_id}
            purchase = {**purchase_input, "repayments": [repayment]}
            invalid_purchases.append((purchase, "Repayment does not belong"))
        for purchase, message in invalid_purchases:
            invalid = await client.put(
                other_path, json={"expectedVersion": 1, "purchases": [purchase]}
            )
            assert invalid.status_code == 422
            assert invalid.json()["error"]["message"].startswith(message)
        assert (await client.get(other_path)).json() == {
            "cookId": str(other_cook_id),
            "rowVersion": 1,
            "purchases": [],
        }
        assert (await client.get(settlements_path)).json() == saved.json()

        params = {"dateFrom": "2026-01-01", "dateTo": "2026-01-12"}
        summary = await client.get("/api/v1/balances", params=params)
        assert summary.status_code == 200
        [buyer] = summary.json()["items"]
        assert buyer["cumulativeBalance"] == -250
        assert buyer["separateOwed"] == 300

        detail = await client.get(path, params=params)
        assert detail.status_code == 200
        purchase_week, repayment_week = detail.json()["weeks"]
        assert purchase_week["separateOwed"] == 300
        assert purchase_week["weeklyDelta"] == -50
        assert purchase_week["purchasesTotal"] == 550
        purchases_by_mode = {event["mode"]: event for event in purchase_week["settlementEvents"]}
        assert purchases_by_mode["separate"]["separateOwed"] == 300
        assert purchases_by_mode["offset"]["separateOwed"] is None
        assert repayment_week["separateOwed"] == 0
        [repayment] = repayment_week["settlementEvents"]
        assert repayment["mode"] == "separate"
        assert repayment["separateOwed"] is None

        for date_to, outstanding in (("2026-01-11", 500), ("2026-01-19", 0)):
            detail = await client.get(path, params={**params, "dateTo": date_to})
            assert detail.status_code == 200
            assert detail.json()["weeks"][0]["separateOwed"] == outstanding

        repayment_only = await client.get(path, params={**params, "dateFrom": "2026-01-12"})
        assert repayment_only.status_code == 200
        [week] = repayment_only.json()["weeks"]
        assert week["separateOwed"] == 0
        assert week["reimbursementsTotal"] == 200
    await engine.dispose()


@pytest.mark.parametrize("amount", [0, -1, 1.5, True])
def test_purchase_amount_requires_positive_integer_rubles(amount):
    with pytest.raises(ValidationError):
        ReplaceSettlementsRequest(
            expected_version=1, purchases=[{"userId": uuid4(), "amount": amount, "mode": "offset"}]
        )


def test_repayment_cannot_exceed_purchase():
    with pytest.raises(ValidationError, match="exceed"):
        ReplaceSettlementsRequest(
            expected_version=1,
            purchases=[
                {
                    "userId": uuid4(),
                    "amount": 100,
                    "mode": "offset",
                    "repayments": [{"amount": 101, "repaymentDate": "2026-01-01"}],
                }
            ],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "repayment", "expected_charge", "expected_separate"),
    [
        ("offset", 0, -200, 0),
        ("offset", 200, 0, 0),
        ("separate", 0, 300, 500),
        ("separate", 500, 300, 0),
    ],
)
async def test_selection_accounts_for_purchase_mode_and_actual_repayment(
    monkeypatch, mode, repayment, expected_charge, expected_separate
):
    user_id, cook_id = uuid4(), uuid4()
    purchase = SimpleNamespace(
        user_id=user_id,
        user_name="Synthetic",
        amount=500,
        mode=mode,
        repayments=[SimpleNamespace(amount=repayment)] if repayment else [],
    )
    monkeypatch.setattr(
        "app.services.settlements.get_settlements",
        AsyncMock(return_value=SimpleNamespace(purchases=[purchase])),
    )
    cook = SimpleNamespace(id=cook_id)
    service = CooksService(SimpleNamespace(get=AsyncMock(return_value=cook)))
    service._load = AsyncMock(
        return_value=SimpleNamespace(
            calculation=SimpleNamespace(status="valid", members=[SimpleNamespace(charge=300)]),
            members=[SimpleNamespace(user_id=user_id)],
            users={user_id: SimpleNamespace(name="Synthetic")},
        )
    )
    result = await service.calculate_selection(SimpleNamespace(cook_ids=[cook_id]))
    assert result.charges[0].charge == expected_charge
    assert sum(p.charge for p in result.separate_owed) == expected_separate
    assert [p.charge for p in result.negative_charges] == (
        [expected_charge] if expected_charge < 0 else []
    )


@pytest.mark.asyncio
async def test_selection_combines_cooks_and_keeps_separate_debt_for_nonparticipant(monkeypatch):
    member_id, buyer_id, first_cook_id, second_cook_id = (uuid4() for _ in range(4))
    first, second = SimpleNamespace(id=first_cook_id), SimpleNamespace(id=second_cook_id)
    service = CooksService(SimpleNamespace(get=AsyncMock(side_effect=[first, second])))

    def loaded(charge):
        return SimpleNamespace(
            calculation=SimpleNamespace(status="valid", members=[SimpleNamespace(charge=charge)]),
            members=[SimpleNamespace(user_id=member_id)],
            users={member_id: SimpleNamespace(name="Member")},
        )

    service._load = AsyncMock(side_effect=[loaded(300), loaded(200)])
    offset = SimpleNamespace(
        user_id=member_id, user_name="Member", amount=450, mode="offset", repayments=[]
    )
    buyer_offset = SimpleNamespace(
        user_id=buyer_id, user_name="Buyer", amount=70, mode="offset", repayments=[]
    )
    buyer_separate = SimpleNamespace(
        user_id=buyer_id,
        user_name="Buyer",
        amount=120,
        mode="separate",
        repayments=[SimpleNamespace(amount=20)],
    )
    monkeypatch.setattr(
        "app.services.settlements.get_settlements",
        AsyncMock(
            side_effect=[
                SimpleNamespace(purchases=[offset]),
                SimpleNamespace(purchases=[buyer_offset, buyer_separate]),
            ]
        ),
    )

    result = await service.calculate_selection(
        SimpleNamespace(cook_ids=[first_cook_id, second_cook_id])
    )

    assert {item.user_id: item.charge for item in result.charges} == {member_id: 50, buyer_id: -70}
    assert result.total == -20
    assert [(item.user_id, item.charge) for item in result.positive_charges] == [(member_id, 50)]
    assert result.positive_total == 50
    assert [(item.user_id, item.charge) for item in result.negative_charges] == [(buyer_id, -70)]
    assert [(item.user_id, item.charge) for item in result.separate_owed] == [(buyer_id, 100)]


@pytest.mark.asyncio
async def test_settlement_http_contract_and_conflict(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.contracts.settlements import SettlementsResponse
    from app.api.routes.settlements import get_session, router

    cook_id = uuid4()
    app = FastAPI()
    app.include_router(router)

    async def fake_session():
        yield SimpleNamespace()

    app.dependency_overrides[get_session] = fake_session
    monkeypatch.setattr(
        "app.api.routes.settlements.get_settlements",
        AsyncMock(return_value=SettlementsResponse(cook_id=cook_id, row_version=2, purchases=[])),
    )
    monkeypatch.setattr(
        "app.api.routes.settlements.replace_settlements",
        AsyncMock(side_effect=VersionConflictError("Changed", details={"currentVersion": 2})),
    )
    with TestClient(app) as client:
        response = client.get(f"/api/v1/cooks/{cook_id}/settlements")
        assert response.json() == {"cookId": str(cook_id), "rowVersion": 2, "purchases": []}
        conflict = client.put(
            f"/api/v1/cooks/{cook_id}/settlements", json={"expectedVersion": 1, "purchases": []}
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["details"] == {"currentVersion": 2}
        assert (
            client.put(
                f"/api/v1/cooks/{cook_id}/settlements", json={"expectedVersion": 0, "purchases": []}
            ).status_code
            == 422
        )


@pytest.mark.asyncio
async def test_locked_version_refreshes_a_previously_loaded_identity():
    from sqlalchemy import update

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Cook.__table__.create(conn))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        cook = Cook(
            id=uuid4(),
            cook_date=date(2026, 1, 5),
            legacy_filename="synthetic",
            source_key="synthetic",
            type_snapshot="Test",
            sale=1,
            total_price_cached=0,
            calculation_version=1,
            row_version=1,
        )
        session.add(cook)
        await session.commit()
        async with engine.begin() as connection:
            await connection.execute(update(Cook).where(Cook.id == cook.id).values(row_version=2))
        assert cook.row_version == 1  # old identity retained after a different writer commits
        with pytest.raises(VersionConflictError) as conflict:
            await replace_settlements(
                session, cook.id, ReplaceSettlementsRequest(expected_version=1, purchases=[])
            )
        assert conflict.value.details == {"currentVersion": 2}
    await engine.dispose()
