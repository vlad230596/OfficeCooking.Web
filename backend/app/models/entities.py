import uuid
from datetime import date, datetime

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('loading', 'validated', 'published', 'failed', 'rolled_back')",
            name="status_allowed",
        ),
        CheckConstraint("calculation_version >= 1", name="calculation_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    manifest_checksum: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    migrator_version: Mapped[str] = mapped_column(Text, nullable=False)
    alembic_revision: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    target_database: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('viewer', 'editor', 'admin')", name="users_role_allowed"),
        Index("uq_users_username_lower", text("lower(username)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    legacy_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    source_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    permanent_sale: Mapped[float] = mapped_column(REAL, nullable=False, server_default=text("1.0"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    username: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'viewer'"))
    auth_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_id", "user_id"),)

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    csrf_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserContact(Base):
    __tablename__ = "user_contacts"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        UniqueConstraint("user_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class PaymentType(Base):
    __tablename__ = "payment_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    legacy_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    source_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_user_id_payment_date", "user_id", "payment_date"),
        Index("ix_payments_payment_date", "payment_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    legacy_position: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    payment_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date_raw: Mapped[str] = mapped_column(Text, nullable=False)
    registration_date_raw: Mapped[str | None] = mapped_column(Text)
    registration_date_parsed: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    sum: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    source_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    included_in_balance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ZenMoneySettings(Base):
    __tablename__ = "zenmoney_settings"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_title: Mapped[str] = mapped_column(Text, nullable=False)
    payment_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_types.id", ondelete="RESTRICT"), nullable=False
    )
    server_timestamp: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ZenMoneyAccountConfig(Base):
    __tablename__ = "zenmoney_account_configs"

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_title: Mapped[str] = mapped_column(Text, nullable=False)
    payment_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_types.id", ondelete="RESTRICT"), nullable=False
    )
    server_timestamp: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ZenMoneyBlacklistEntry(Base):
    __tablename__ = "zenmoney_blacklist_entries"
    __table_args__ = (
        Index("uq_zenmoney_blacklist_pattern_lower", text("lower(pattern)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)


class ZenMoneyMatchRule(Base):
    __tablename__ = "zenmoney_match_rules"
    __table_args__ = (
        CheckConstraint("kind IN ('phone', 'name')", name="kind_allowed"),
        UniqueConstraint("kind", "pattern"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class ZenMoneyTransaction(Base):
    __tablename__ = "zenmoney_transactions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('matched', 'review', 'blacklisted', 'rejected')",
            name="status_allowed",
        ),
        CheckConstraint(
            "decision_source IN ('automatic', 'manual')", name="decision_source_allowed"
        ),
        Index("ix_zenmoney_transactions_date", text("transaction_date DESC")),
        Index("ix_zenmoney_transactions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    zenmoney_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    changed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(REAL, nullable=False)
    payee: Mapped[str | None] = mapped_column(Text)
    original_payee: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    hold: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    decision_source: Mapped[str] = mapped_column(Text, nullable=False)
    match_reason: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), unique=True
    )


class BalanceAdjustment(Base):
    __tablename__ = "balance_adjustments"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="amount_nonzero"),
        CheckConstraint("length(trim(reason)) > 0", name="reason_nonempty"),
        Index("ix_balance_adjustments_user_date", "user_id", "adjustment_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    adjustment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_before: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class CookTemplate(TimestampMixin, Base):
    __tablename__ = "cook_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    legacy_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    is_multivote: Mapped[bool] = mapped_column(Boolean, nullable=False)


class TemplateVoteVariant(Base):
    __tablename__ = "template_vote_variants"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        UniqueConstraint("template_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cook_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float] = mapped_column(REAL, nullable=False)


class TemplateIngredient(Base):
    __tablename__ = "template_ingredients"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        UniqueConstraint("template_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cook_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Cook(TimestampMixin, Base):
    __tablename__ = "cooks"
    __table_args__ = (
        Index("ix_cooks_template_id_cook_date_desc", "template_id", text("cook_date DESC")),
        CheckConstraint("calculation_version >= 1", name="calculation_version_positive"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cook_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    legacy_filename: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cook_templates.id", ondelete="SET NULL")
    )
    type_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    sale: Mapped[float] = mapped_column(REAL, nullable=False)
    total_price_cached: Mapped[float | None] = mapped_column(REAL)
    calculation_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class CookVoteVariant(Base):
    __tablename__ = "cook_vote_variants"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        UniqueConstraint("cook_id", "position"),
        UniqueConstraint("cook_id", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cooks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float] = mapped_column(REAL, nullable=False)


class CookMember(Base):
    __tablename__ = "cook_members"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        UniqueConstraint("cook_id", "user_id"),
        UniqueConstraint("cook_id", "position"),
        UniqueConstraint("cook_id", "id"),
        Index("ix_cook_members_user_id_cook_id", "user_id", "cook_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cooks.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    permanent_sale_snapshot: Mapped[float] = mapped_column(REAL, nullable=False)


class CookMemberVote(Base):
    __tablename__ = "cook_member_votes"
    __table_args__ = (
        PrimaryKeyConstraint("cook_member_id", "position"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        ForeignKeyConstraint(
            ("cook_id", "cook_member_id"),
            ("cook_members.cook_id", "cook_members.id"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("cook_id", "cook_vote_variant_id"),
            ("cook_vote_variants.cook_id", "cook_vote_variants.id"),
            ondelete="CASCADE",
        ),
    )

    cook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cook_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cook_vote_variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class CookProductPrice(Base):
    __tablename__ = "cook_product_prices"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint(
            "calculation_status IN ('valid', 'empty', 'error')",
            name="calculation_status_allowed",
        ),
        CheckConstraint(
            "((calculation_status IN ('valid', 'empty') "
            "AND computed_value IS NOT NULL AND calculation_error IS NULL) "
            "OR (calculation_status = 'error' AND computed_value IS NULL "
            "AND calculation_error IS NOT NULL AND length(calculation_error) > 0))",
            name="calculation_fields_consistent",
        ),
        CheckConstraint("calculation_version >= 1", name="calculation_version_positive"),
        UniqueConstraint("cook_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cooks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_name: Mapped[str | None] = mapped_column(Text)
    expression: Mapped[str | None] = mapped_column(Text)
    computed_value: Mapped[float | None] = mapped_column(REAL)
    calculation_status: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_error: Mapped[str | None] = mapped_column(Text)
    calculation_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
