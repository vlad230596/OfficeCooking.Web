from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from .base import ApiModel

EnabledFilter = Literal["true", "false", "all"]


class UsersQuery(ApiModel):
    enabled: EnabledFilter = "all"


class UserContactResponse(ApiModel):
    position: int = Field(ge=0)
    value: str


class UserContactInput(ApiModel):
    value: str = Field(min_length=1, max_length=500)

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("contact must not be blank")
        return value


class SaveUserRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    permanent_sale: float
    enabled: bool
    contacts: list[UserContactInput] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class UserResponse(ApiModel):
    id: UUID
    legacy_id: int = Field(ge=0)
    name: str = Field(min_length=1)
    permanent_sale: float
    enabled: bool
    contacts: list[UserContactResponse] = Field(default_factory=list)
