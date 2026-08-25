from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api.contracts.templates import SaveTemplateRequest
from app.api.contracts.users import SaveUserRequest
from app.api.routes.catalog import get_catalog_session, router
from app.models import (
    CookTemplate,
    TemplateIngredient,
    TemplateVoteVariant,
    User,
    UserContact,
)
from app.services.catalog import (
    create_user,
    get_template,
    list_templates,
    list_users,
    update_template,
)


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class FakeResult:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def scalars(self) -> FakeScalars:
        return FakeScalars(self.values)

    def scalar_one_or_none(self) -> object | None:
        assert len(self.values) <= 1
        return self.values[0] if self.values else None


class FakeSession:
    def __init__(self, rows: dict[type[object], list[object]]) -> None:
        self.rows = rows
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        entity = statement.column_descriptions[0]["entity"]  # type: ignore[attr-defined]
        return FakeResult(self.rows.get(entity, []))


def _catalog_rows() -> tuple[dict[type[object], list[object]], UUID]:
    template_id = uuid4()
    user_id = uuid4()
    rows: dict[type[object], list[object]] = {
        User: [
            SimpleNamespace(
                id=user_id,
                legacy_id=7,
                name="Ирина",
                permanent_sale=0.9,
                enabled=True,
            )
        ],
        UserContact: [SimpleNamespace(user_id=user_id, position=0, value="@irina")],
        CookTemplate: [
            SimpleNamespace(
                id=template_id,
                legacy_name="Салат",
                is_multivote=True,
            )
        ],
        TemplateVoteVariant: [SimpleNamespace(id=uuid4(), position=0, name="Большой", value=1.5)],
        TemplateIngredient: [SimpleNamespace(id=uuid4(), position=0, name="Огурцы", enabled=False)],
    }
    return rows, template_id


@pytest.mark.asyncio
async def test_catalog_services_serialize_contracts_and_build_stable_orders() -> None:
    rows, template_id = _catalog_rows()
    session = FakeSession(rows)

    users = await list_users(session, "true")  # type: ignore[arg-type]
    summaries = await list_templates(session)  # type: ignore[arg-type]
    detail = await get_template(session, template_id)  # type: ignore[arg-type]

    assert users[0].model_dump(mode="json") == {
        "id": str(rows[User][0].id),
        "legacyId": 7,
        "name": "Ирина",
        "permanentSale": 0.9,
        "enabled": True,
        "contacts": [{"position": 0, "value": "@irina"}],
    }
    assert summaries[0].name == "Салат"
    assert detail is not None
    assert detail.ingredients[0].enabled is False

    sql = [str(statement) for statement in session.statements]
    assert "users.legacy_id, users.name, users.id" in sql[0]
    assert "user_contacts.position" in sql[1]
    assert "cook_templates.legacy_name, cook_templates.id" in sql[2]
    assert "template_vote_variants.position" in sql[4]
    assert "template_ingredients.position" in sql[5]


@pytest.mark.asyncio
async def test_catalog_http_routes_use_overrideable_session_dependency() -> None:
    rows, template_id = _catalog_rows()
    session = FakeSession(rows)
    app = FastAPI()
    app.include_router(router)

    async def override_session() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_catalog_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        users_response = await client.get("/api/v1/users?enabled=true")
        templates_response = await client.get("/api/v1/templates")
        detail_response = await client.get(f"/api/v1/templates/{template_id}")

    assert users_response.status_code == 200
    assert users_response.json()[0]["legacyId"] == 7
    assert templates_response.json()[0]["name"] == "Салат"
    assert detail_response.json()["ingredients"][0]["enabled"] is False


@pytest.mark.asyncio
async def test_missing_template_has_stable_error_envelope() -> None:
    session = FakeSession({CookTemplate: []})
    app = FastAPI()
    app.include_router(router)

    async def override_session() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_catalog_session] = override_session
    missing_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/templates/{missing_id}", headers={"x-request-id": "test-request"}
        )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "template_not_found",
            "message": "Template was not found.",
            "fieldErrors": [],
            "details": {"templateId": str(missing_id)},
            "requestId": "test-request",
        }
    }


@pytest.mark.asyncio
async def test_create_user_allocates_next_legacy_id_and_preserves_contact_order() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=47)
    session.commit = AsyncMock()
    request = SaveUserRequest.model_validate(
        {
            "name": "Новый участник",
            "permanentSale": 0.75,
            "enabled": True,
            "contacts": [{"value": "@new"}, {"value": "Новый участник"}],
        }
    )

    response = await create_user(session, request)

    added_user = session.add.call_args.args[0]
    added_contacts = session.add_all.call_args.args[0]
    assert added_user.legacy_id == 48
    assert added_user.source_key == f"web:users:{added_user.id}"
    assert [item.position for item in added_contacts] == [0, 1]
    assert response.contacts[1].value == "Новый участник"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_dish_replaces_editable_children_without_changing_identity() -> None:
    template_id = uuid4()
    template = CookTemplate(
        id=template_id,
        legacy_name="Салат",
        source_key="Templates/Салат.json",
        is_multivote=False,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=template)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    request = SaveTemplateRequest.model_validate(
        {
            "name": "Большой салат",
            "isMultivote": True,
            "voteVariants": [{"name": "Половина", "value": 0.5}],
            "ingredients": [{"name": "Огурцы", "enabled": False}],
        }
    )

    response = await update_template(session, template_id, request)

    assert response.id == template_id
    assert template.source_key == "Templates/Салат.json"
    assert response.name == "Большой салат"
    assert response.vote_variants[0].position == 0
    assert response.ingredients[0].enabled is False
    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()


def test_catalog_mutations_reject_blank_names_and_non_finite_coefficients() -> None:
    with pytest.raises(ValidationError):
        SaveUserRequest.model_validate(
            {"name": "  ", "permanentSale": float("inf"), "enabled": True, "contacts": []}
        )
    with pytest.raises(ValidationError):
        SaveTemplateRequest.model_validate(
            {
                "name": "Суп",
                "voteVariants": [{"name": " ", "value": 1}],
                "ingredients": [],
            }
        )
