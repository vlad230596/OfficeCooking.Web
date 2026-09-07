from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, model_validator

from .base import ApiModel

ZenMoneyStatus = Literal["matched", "review", "blacklisted", "rejected"]


class ZenMoneyAccountResponse(ApiModel):
    id: str
    title: str
    company_title: str | None = None
    sync_ids: list[str] = Field(default_factory=list)
    archived: bool = False


class ZenMoneyAccountsRequest(ApiModel):
    access_token: SecretStr | None = None


class ZenMoneyPaymentTypeResponse(ApiModel):
    id: UUID
    name: str


class ZenMoneyConfiguredAccountResponse(ApiModel):
    account_id: str
    account_title: str
    payment_type_id: UUID
    server_timestamp: int
    last_sync_at: datetime | None = None
    blacklist: list[str] = Field(default_factory=list)


class ZenMoneySettingsResponse(ApiModel):
    configured: bool
    token_configured: bool
    account_id: str | None = None
    account_title: str | None = None
    payment_type_id: UUID | None = None
    server_timestamp: int = 0
    last_sync_at: datetime | None = None
    accounts: list[ZenMoneyConfiguredAccountResponse] = Field(default_factory=list)
    payment_types: list[ZenMoneyPaymentTypeResponse] = Field(default_factory=list)


class SaveZenMoneyAccountRequest(ApiModel):
    account_id: str = Field(min_length=1, max_length=200)
    account_title: str = Field(min_length=1, max_length=500)
    payment_type_id: UUID
    blacklist: list[str] = Field(default_factory=list, max_length=500)


class SaveZenMoneySettingsRequest(ApiModel):
    access_token: SecretStr | None = None
    accounts: list[SaveZenMoneyAccountRequest] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def normalize_blacklist(self) -> SaveZenMoneySettingsRequest:
        account_ids = [value.account_id for value in self.accounts]
        if len(set(account_ids)) != len(account_ids):
            raise ValueError("account IDs must be unique")
        for account in self.accounts:
            values = [value.strip() for value in account.blacklist if value.strip()]
            if len({value.casefold() for value in values}) != len(values):
                raise ValueError("blacklist entries must be unique within an account")
            account.blacklist = values
        return self


class ZenMoneySyncResponse(ApiModel):
    received: int
    created: int
    updated: int
    matched: int
    review: int
    blacklisted: int
    server_timestamp: int


class ZenMoneyBulkApproveResponse(ApiModel):
    approved: int
    skipped: int


class ZenMoneyTransactionResponse(ApiModel):
    id: UUID
    account_id: str
    account_title: str
    transaction_date: date
    amount: float
    payee: str | None = None
    original_payee: str | None = None
    comment: str | None = None
    hold: bool
    deleted: bool
    status: ZenMoneyStatus
    decision_source: Literal["automatic", "manual"]
    match_reason: str | None = None
    user_id: UUID | None = None
    user_name: str | None = None
    payment_id: UUID | None = None


class DecideZenMoneyTransactionRequest(ApiModel):
    action: Literal["assign", "approve", "reject", "retry", "blacklist"]
    user_id: UUID | None = None

    @model_validator(mode="after")
    def require_user_for_assignment(self) -> DecideZenMoneyTransactionRequest:
        if (self.action == "assign") != (self.user_id is not None):
            raise ValueError("userId is required only for assign")
        return self
