"""Purchases financed by participants and actual organizer reimbursements."""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CookPurchase(Base):
    __tablename__ = "cook_purchases"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("mode IN ('offset', 'separate')", name="mode_allowed"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        UniqueConstraint("cook_id", "position"),
        Index("ix_cook_purchases_user_cook", "user_id", "cook_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cooks.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)


class CookReimbursement(Base):
    __tablename__ = "cook_reimbursements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_cook_reimbursements_date", "repayment_date"),
        Index("ix_cook_reimbursements_purchase_date", "purchase_id", "repayment_date"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    purchase_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cook_purchases.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    repayment_date: Mapped[date] = mapped_column(Date, nullable=False)
