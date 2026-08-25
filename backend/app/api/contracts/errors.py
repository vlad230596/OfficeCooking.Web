from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import ApiModel


class FieldError(ApiModel):
    field: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ApiError(ApiModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    field_errors: list[FieldError] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(min_length=1)


class ErrorEnvelope(ApiModel):
    error: ApiError
