from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.authentication import (
    Principal,
    create_auth_session,
    digest_token,
    has_role,
    hash_password,
    required_role,
    verify_password,
)
from app.config import Settings


class FakeWriteSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        pass


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)


def test_tokens_use_fixed_length_one_way_digest() -> None:
    assert len(digest_token("secret")) == 64
    assert digest_token("secret") != "secret"


def test_role_hierarchy() -> None:
    def principal(role: str) -> Principal:
        return Principal(uuid4(), "User", "user", role, "token")  # type: ignore[arg-type]

    assert has_role(principal("admin"), "viewer")
    assert has_role(principal("editor"), "editor")
    assert not has_role(principal("viewer"), "editor")


def test_route_permissions_match_the_public_role_matrix() -> None:
    def request(method: str, path: str) -> SimpleNamespace:
        return SimpleNamespace(method=method, url=SimpleNamespace(path=path))

    assert required_role(request("GET", "/api/v1/balances")) == "viewer"  # type: ignore[arg-type]
    assert required_role(request("POST", "/api/v1/cooks")) == "editor"  # type: ignore[arg-type]
    assert required_role(request("PUT", "/api/v1/users/1")) == "admin"  # type: ignore[arg-type]
    assert required_role(request("GET", "/api/v1/auth/accounts")) == "admin"  # type: ignore[arg-type]
    assert required_role(request("POST", "/api/v1/auth/logout")) == "viewer"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_browser_session_has_a_bounded_server_lifetime() -> None:
    user = SimpleNamespace(id=uuid4())
    browser_session = FakeWriteSession()
    settings = Settings(session_ttl_hours=12)
    before = datetime.now(UTC)

    _, _, browser_expiry = await create_auth_session(
        browser_session,
        user,
        settings,  # type: ignore[arg-type]
    )

    assert before + timedelta(hours=11, minutes=59) < browser_expiry < before + timedelta(hours=13)
