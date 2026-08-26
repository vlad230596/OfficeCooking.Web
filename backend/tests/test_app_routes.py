from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        allowed_hosts=["testserver"],
        cors_origins=["http://testserver"],
    )


def test_application_exposes_the_complete_v1_route_surface() -> None:
    app = create_app(_settings())
    paths = app.openapi()["paths"]

    assert {
        "/health",
        "/ready",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/accounts",
        "/api/v1/auth/accounts/{user_id}",
        "/api/v1/users",
        "/api/v1/templates",
        "/api/v1/templates/{template_id}",
        "/api/v1/cooks",
        "/api/v1/cooks/{cook_id}",
        "/api/v1/cooks/calculate-selection",
        "/api/v1/cooks/preview",
        "/api/v1/calculations/expressions/preview",
        "/api/v1/balances",
        "/api/v1/balances/users/{userId}",
    }.issubset(paths)


def test_request_id_is_preserved_or_generated() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        supplied = client.get("/health", headers={"x-request-id": "route-test.1"})
        generated = client.get("/health", headers={"x-request-id": "invalid id"})

    assert supplied.headers["x-request-id"] == "route-test.1"
    assert generated.headers["x-request-id"]
    assert generated.headers["x-request-id"] != "invalid id"


def test_v1_api_requires_authentication_but_health_remains_public() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        protected = client.get("/api/v1/users")
        health = client.get("/health")

    assert protected.status_code == 401
    assert protected.json()["error"]["code"] == "authentication_required"
    assert protected.headers["x-request-id"]
    assert health.status_code == 200
