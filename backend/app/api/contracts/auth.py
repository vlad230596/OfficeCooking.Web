from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from .base import ApiModel

Role = Literal["viewer", "editor", "admin"]


class LoginRequest(ApiModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class CurrentUserResponse(ApiModel):
    id: UUID
    name: str
    username: str
    role: Role


class AccountResponse(CurrentUserResponse):
    auth_enabled: bool


class UpdateAccountRequest(ApiModel):
    username: str | None = Field(default=None, min_length=3, max_length=100)
    password: str | None = Field(default=None, min_length=12, max_length=1024)
    role: Role
    auth_enabled: bool

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized or any(
            not (c.isascii() and (c.isalnum() or c in "._-")) for c in normalized
        ):
            raise ValueError(
                "username may contain only ASCII letters, digits, dot, dash, underscore"
            )
        return normalized
