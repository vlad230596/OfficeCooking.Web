from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _parse_iso_date(value: Any) -> date:
    if isinstance(value, datetime):
        raise ValueError("datetime is not an API date")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("date must use yyyy-MM-dd")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("date must use yyyy-MM-dd") from error
    if parsed.isoformat() != value:
        raise ValueError("date must use yyyy-MM-dd")
    return parsed


IsoDate = Annotated[date, BeforeValidator(_parse_iso_date)]


class ApiModel(BaseModel):
    """Base for the public v1 JSON contract."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        allow_inf_nan=False,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=False,
    )
