from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import ApiModel


class PageQuery(ApiModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class SortField(ApiModel):
    field: str = Field(min_length=1)
    direction: Literal["asc", "desc"]


class OrderingMetadata(ApiModel):
    fields: list[SortField] = Field(min_length=1)


class Page[T](ApiModel):
    items: list[T]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    ordering: OrderingMetadata

    @model_validator(mode="after")
    def validate_page_counts(self) -> Page[T]:
        expected = (self.total_items + self.page_size - 1) // self.page_size
        if self.total_pages != expected:
            raise ValueError("totalPages does not match totalItems and pageSize")
        return self
