import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


def local_settings() -> Settings:
    return Settings(allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@pytest.mark.asyncio
async def test_health_is_available_without_database_connection() -> None:
    app = create_app(local_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_unknown_host_is_rejected() -> None:
    app = create_app(local_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://attacker.example"
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_allowed_origin_gets_explicit_cors_header() -> None:
    app = create_app(local_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/health", headers={"origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.asyncio
async def test_unknown_origin_gets_no_cors_header() -> None:
    app = create_app(local_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/health", headers={"origin": "http://attacker.example"})

    assert "access-control-allow-origin" not in response.headers
