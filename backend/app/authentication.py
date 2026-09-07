from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import AuthSession, User

Role = Literal["viewer", "editor", "admin"]
SESSION_COOKIE = "office_cook_session"
CSRF_COOKIE = "office_cook_csrf"
CSRF_HEADER = "x-csrf-token"
_ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    name: str
    username: str
    role: Role
    token_hash: str


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("password must contain between 12 and 1024 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(expected)),
        )
        return hmac.compare_digest(derived.hex(), expected)
    except (ValueError, TypeError, MemoryError):
        return False


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_auth_session(
    session: AsyncSession, user: User, settings: Settings
) -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=settings.session_ttl_hours)
    session.add(
        AuthSession(
            token_hash=digest_token(token),
            user_id=user.id,
            csrf_token_hash=digest_token(csrf_token),
            created_at=now,
            expires_at=expires_at,
        )
    )
    await session.commit()
    return token, csrf_token, expires_at


async def authenticate_session(session: AsyncSession, token: str) -> Principal | None:
    result = await session.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == digest_token(token))
    )
    row = result.one_or_none()
    if row is None:
        return None
    auth_session, user = row
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        # SQLite drops timezone metadata even for DateTime(timezone=True).
        # Values are always written as UTC, so restore that information here.
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC) or not user.auth_enabled:
        await session.delete(auth_session)
        await session.commit()
        return None
    if not user.username or not user.password_hash or user.role not in _ROLE_RANK:
        return None
    return Principal(user.id, user.name, user.username, user.role, auth_session.token_hash)


async def revoke_user_sessions(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


def has_role(principal: Principal, required: Role) -> bool:
    return _ROLE_RANK[principal.role] >= _ROLE_RANK[required]


def required_role(request: Request) -> Role:
    path = request.url.path
    if path == "/api/v1/auth/logout":
        return "viewer"
    if path.startswith("/api/v1/auth/accounts"):
        return "admin"
    if path.startswith("/api/v1/zenmoney/settings"):
        return "admin"
    if path.startswith("/api/v1/zenmoney"):
        return "editor"
    if request.method in {"POST", "PUT", "PATCH"}:
        if path.startswith("/api/v1/users") or path.startswith("/api/v1/templates"):
            return "admin"
        return "editor"
    return "viewer"
