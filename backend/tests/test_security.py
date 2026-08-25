import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


def app_with_mutation_route() -> FastAPI:
    app = create_app(Settings(allowed_hosts=["localhost", "127.0.0.1", "testserver"]))

    @app.post("/_test/mutation")
    async def mutation() -> dict[str, bool]:
        return {"accepted": True}

    @app.delete("/_test/mutation")
    async def delete_mutation() -> dict[str, bool]:
        return {"deleted": True}

    return app


@pytest.mark.asyncio
async def test_mutation_rejects_form_content_type() -> None:
    app = app_with_mutation_route()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/_test/mutation", data={"value": "1"})

    assert response.status_code == 415


@pytest.mark.asyncio
async def test_mutation_accepts_json_content_type() -> None:
    app = app_with_mutation_route()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/_test/mutation", json={"value": 1})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_is_explicitly_disabled() -> None:
    app = app_with_mutation_route()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.delete("/_test/mutation")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET, POST, PUT, PATCH, OPTIONS"
    assert response.json() == {
        "detail": "DELETE is not available in the current API version."
    }
