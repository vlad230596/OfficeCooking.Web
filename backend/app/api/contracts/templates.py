from __future__ import annotations

from uuid import UUID

from pydantic import Field, field_validator

from .base import ApiModel


class TemplateVoteVariantResponse(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    name: str = Field(min_length=1)
    value: float


class TemplateIngredientResponse(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    name: str = Field(min_length=1)
    enabled: bool


class TemplateSummaryResponse(ApiModel):
    id: UUID
    name: str = Field(min_length=1)
    is_multivote: bool


class TemplateDetailResponse(TemplateSummaryResponse):
    vote_variants: list[TemplateVoteVariantResponse]
    ingredients: list[TemplateIngredientResponse]


class TemplateVoteVariantInput(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    value: float

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class TemplateIngredientInput(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class SaveTemplateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    is_multivote: bool = False
    vote_variants: list[TemplateVoteVariantInput] = Field(default_factory=list, max_length=100)
    ingredients: list[TemplateIngredientInput] = Field(default_factory=list, max_length=200)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value
