from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .base import ApiModel


class CalculationStatus(StrEnum):
    VALID = "valid"
    EMPTY = "empty"
    ERROR = "error"


class ExpressionPreviewRequest(ApiModel):
    expression: str | None = Field(default=None, max_length=4096)


class ExpressionPreviewResponse(ApiModel):
    expression: str | None
    status: CalculationStatus
    computed_value: float | None
    error: str | None
    calculation_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_calculation_fields(self) -> ExpressionPreviewResponse:
        if self.status is CalculationStatus.ERROR:
            if self.computed_value is not None or not self.error:
                raise ValueError("error result requires only a non-empty error")
        elif self.computed_value is None or self.error is not None:
            raise ValueError("valid and empty results require a value and no error")
        return self
