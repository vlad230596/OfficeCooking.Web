from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TemplatePreparation(Base):
    __tablename__ = "template_preparations"
    __table_args__ = (CheckConstraint("version >= 1", name="version_positive"),)

    template_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cook_templates.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)


class CookPreparation(Base):
    __tablename__ = "cook_preparations"

    cook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cooks.id", ondelete="CASCADE"), primary_key=True
    )
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    groups: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
