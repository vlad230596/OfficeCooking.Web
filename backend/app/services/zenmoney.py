from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts.zenmoney import (
    SaveZenMoneySettingsRequest,
    ZenMoneyAccountResponse,
    ZenMoneyBulkApproveResponse,
    ZenMoneyPaymentTypeResponse,
    ZenMoneySettingsResponse,
    ZenMoneySyncResponse,
    ZenMoneyTransactionResponse,
)
from app.config import Settings
from app.models import (
    Payment,
    PaymentType,
    User,
    UserContact,
    ZenMoneyBlacklistEntry,
    ZenMoneyMatchRule,
    ZenMoneySettings,
    ZenMoneyTransaction,
)

ZENMONEY_DIFF_URL = "https://api.zenmoney.ru/v8/diff/"
_TRANSACTION_NAMESPACE = uuid.UUID("ea925fd2-894a-4d4c-88ad-cc58e267097f")
_SPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w+]+", re.UNICODE)


class ZenMoneyError(RuntimeError):
    def __init__(self, message: str, *, code: str = "zenmoney_error", status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class MatchResult:
    status: str
    user_id: UUID | None
    reason: str


@dataclass(frozen=True)
class LearnedRule:
    kind: str
    pattern: str
    user_id: UUID


def _fernet(settings: Settings) -> Fernet:
    secret = settings.zenmoney_encryption_key
    if secret is None or not secret.get_secret_value():
        raise ZenMoneyError(
            "ZenMoney encryption key is not configured on the server.",
            code="encryption_key_missing",
            status_code=503,
        )
    try:
        return Fernet(secret.get_secret_value().encode())
    except (ValueError, TypeError) as error:
        raise ZenMoneyError(
            "ZenMoney encryption key is invalid.",
            code="encryption_key_invalid",
            status_code=503,
        ) from error


def encrypt_token(token: str, settings: Settings) -> str:
    value = token.strip()
    if not value:
        raise ZenMoneyError("Access token must not be empty.", code="token_required")
    return _fernet(settings).encrypt(value.encode()).decode()


def decrypt_token(ciphertext: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken as error:
        raise ZenMoneyError(
            "Stored ZenMoney token cannot be decrypted.",
            code="token_decryption_failed",
            status_code=503,
        ) from error


async def request_diff(token: str, server_timestamp: int) -> dict[str, Any]:
    payload = {
        "currentClientTimestamp": int(datetime.now(UTC).timestamp()),
        "serverTimestamp": server_timestamp,
    }
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.post(
                ZENMONEY_DIFF_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code in {401, 403}:
            raise ZenMoneyError("ZenMoney rejected the access token.", code="invalid_token")
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict) or not isinstance(value.get("serverTimestamp"), int):
            raise ValueError("invalid diff response")
        return value
    except ZenMoneyError:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise ZenMoneyError(
            "Could not load data from ZenMoney.",
            code="zenmoney_unavailable",
            status_code=502,
        ) from error


def accounts_from_diff(diff: dict[str, Any]) -> list[ZenMoneyAccountResponse]:
    companies = {
        item.get("id"): item.get("title")
        for item in diff.get("company", [])
        if isinstance(item, dict)
    }
    result = []
    for item in diff.get("account", []):
        if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
            continue
        result.append(
            ZenMoneyAccountResponse(
                id=str(item["id"]),
                title=str(item["title"]),
                company_title=companies.get(item.get("company")),
                sync_ids=[str(value) for value in item.get("syncID") or []],
                archived=bool(item.get("archive", False)),
            )
        )
    return sorted(result, key=lambda item: (item.archived, item.company_title or "", item.title))


async def get_settings_response(session: AsyncSession) -> ZenMoneySettingsResponse:
    configured = await session.get(ZenMoneySettings, 1)
    payment_types = (
        await session.execute(
            select(PaymentType).where(PaymentType.enabled.is_(True)).order_by(PaymentType.name)
        )
    ).scalars()
    blacklist = (
        await session.execute(
            select(ZenMoneyBlacklistEntry.pattern).order_by(ZenMoneyBlacklistEntry.pattern)
        )
    ).scalars()
    return ZenMoneySettingsResponse(
        configured=configured is not None,
        token_configured=configured is not None,
        account_id=configured.account_id if configured else None,
        account_title=configured.account_title if configured else None,
        payment_type_id=configured.payment_type_id if configured else None,
        server_timestamp=configured.server_timestamp if configured else 0,
        last_sync_at=configured.last_sync_at if configured else None,
        blacklist=list(blacklist),
        payment_types=[
            ZenMoneyPaymentTypeResponse(id=item.id, name=item.name) for item in payment_types
        ],
    )


async def save_settings(
    session: AsyncSession, request: SaveZenMoneySettingsRequest, settings: Settings
) -> ZenMoneySettingsResponse:
    payment_type = await session.get(PaymentType, request.payment_type_id)
    if payment_type is None or not payment_type.enabled:
        raise ZenMoneyError("Payment type was not found.", code="payment_type_not_found")
    current = await session.get(ZenMoneySettings, 1)
    if current is None and request.access_token is None:
        raise ZenMoneyError("Access token is required.", code="token_required")
    supplied_token = (
        request.access_token.get_secret_value()
        if request.access_token is not None
        else decrypt_token(current.access_token_ciphertext, settings)  # type: ignore[union-attr]
    )
    available_accounts = accounts_from_diff(await request_diff(supplied_token, 0))
    selected_account = next(
        (account for account in available_accounts if account.id == request.account_id), None
    )
    if selected_account is None:
        raise ZenMoneyError(
            "Selected account was not returned by ZenMoney.", code="account_not_found"
        )
    selected_title = " · ".join(
        value for value in (selected_account.company_title, selected_account.title) if value
    )
    if current is None:
        current = ZenMoneySettings(
            id=1,
            access_token_ciphertext=encrypt_token(
                request.access_token.get_secret_value(),
                settings,  # type: ignore[union-attr]
            ),
            account_id=request.account_id,
            account_title=selected_title,
            payment_type_id=request.payment_type_id,
            server_timestamp=0,
        )
        session.add(current)
    else:
        if request.access_token is not None:
            current.access_token_ciphertext = encrypt_token(
                request.access_token.get_secret_value(), settings
            )
        if request.access_token is not None or current.account_id != request.account_id:
            current.server_timestamp = 0
        current.account_id = request.account_id
        current.account_title = selected_title
        current.payment_type_id = request.payment_type_id
    await session.execute(delete(ZenMoneyBlacklistEntry))
    session.add_all(
        [ZenMoneyBlacklistEntry(id=uuid.uuid4(), pattern=value) for value in request.blacklist]
    )
    await session.flush()
    users = await _users_with_contacts(session)
    learned_rules = await _learned_rules(session)
    current_blacklist = request.blacklist
    automatic = (
        await session.execute(
            select(ZenMoneyTransaction).where(
                ZenMoneyTransaction.account_id == current.account_id,
                ZenMoneyTransaction.decision_source == "automatic",
                ZenMoneyTransaction.deleted.is_(False),
            )
        )
    ).scalars()
    for transaction in automatic:
        if transaction.hold:
            transaction.status = "review"
            transaction.user_id = None
            transaction.match_reason = "transaction is on hold"
            await _deactivate_payment(session, transaction)
            continue
        sender = " ".join(
            value
            for value in (
                transaction.payee,
                transaction.original_payee,
                transaction.comment,
            )
            if value
        )
        match = match_sender(sender, users, current_blacklist, learned_rules)
        transaction.status = match.status
        transaction.user_id = match.user_id
        transaction.match_reason = match.reason
        if transaction.status == "matched" and transaction.payment_id is not None:
            await _upsert_payment(session, transaction, current, create_if_missing=False)
        else:
            await _deactivate_payment(session, transaction)
    manual_matches = (
        await session.execute(
            select(ZenMoneyTransaction).where(
                ZenMoneyTransaction.account_id == current.account_id,
                ZenMoneyTransaction.decision_source == "manual",
                ZenMoneyTransaction.status == "matched",
            )
        )
    ).scalars()
    for transaction in manual_matches:
        if transaction.payment_id is not None:
            await _upsert_payment(session, transaction, current, create_if_missing=False)
    await session.commit()
    return await get_settings_response(session)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _SPACE.sub(" ", _NON_WORD.sub(" ", value.casefold().replace("ё", "е"))).strip()


def normalize_phone(value: str | None) -> str:
    digits = "".join(character for character in value or "" if character.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def _name_alias_matches(alias: str, haystack: str) -> bool:
    if not alias or not haystack:
        return False
    if alias in haystack:
        return True
    alias_parts = alias.split()[:2]
    haystack_parts = haystack.split()
    if len(alias_parts) < 2:
        return False
    for index in range(len(haystack_parts) - 1):
        candidate = haystack_parts[index : index + 2]
        if not any(
            left == right and len(left) >= 3
            for left, right in zip(alias_parts, candidate, strict=True)
        ):
            continue
        if all(
            left.startswith(right) or right.startswith(left)
            for left, right in zip(alias_parts, candidate, strict=True)
        ):
            return True
    return False


def match_sender(
    haystack: str,
    users: list[tuple[User, list[str]]],
    blacklist: list[str],
    learned_rules: list[LearnedRule] | None = None,
) -> MatchResult:
    normalized = normalize_text(haystack)
    phone = normalize_phone(haystack)
    for pattern in blacklist:
        pattern_text = normalize_text(pattern)
        pattern_phone = normalize_phone(pattern)
        if (pattern_text and pattern_text in normalized) or (
            pattern_phone and pattern_phone in phone
        ):
            return MatchResult("blacklisted", None, f"blacklist: {pattern}")

    rule_matches: set[UUID] = set()
    rule_kinds: set[str] = set()
    for rule in learned_rules or []:
        matches = (rule.kind == "phone" and bool(phone) and rule.pattern == phone) or (
            rule.kind == "name" and bool(rule.pattern) and rule.pattern in normalized
        )
        if matches:
            rule_matches.add(rule.user_id)
            rule_kinds.add(rule.kind)
    if len(rule_matches) == 1:
        kind = "phone" if "phone" in rule_kinds else "name"
        return MatchResult("matched", next(iter(rule_matches)), f"learned {kind}")
    if len(rule_matches) > 1:
        return MatchResult("review", None, "ambiguous learned rule")

    contact_matches: set[UUID] = set()
    contact_kinds: set[str] = set()
    for user, contacts in users:
        for contact in contacts:
            contact_phone = normalize_phone(contact)
            contact_text = normalize_text(contact)
            if contact_phone and contact_phone in phone:
                contact_matches.add(user.id)
                contact_kinds.add("phone")
            elif contact_text and contact_text in normalized:
                contact_matches.add(user.id)
                contact_kinds.add("name")
    if len(contact_matches) == 1:
        kind = "phone" if "phone" in contact_kinds else "saved name"
        return MatchResult("matched", next(iter(contact_matches)), kind)
    if len(contact_matches) > 1:
        return MatchResult("review", None, "ambiguous contact")

    name_matches: set[UUID] = set()
    for user, _ in users:
        name = normalize_text(user.name)
        parts = name.split()
        aliases = {name}
        if len(parts) >= 2:
            aliases.add(f"{parts[1]} {parts[0]}")
        if any(_name_alias_matches(alias, normalized) for alias in aliases):
            name_matches.add(user.id)
    if len(name_matches) == 1:
        return MatchResult("matched", next(iter(name_matches)), "name")
    if len(name_matches) > 1:
        return MatchResult("review", None, "ambiguous name")
    return MatchResult("review", None, "no unique user match")


async def _users_with_contacts(session: AsyncSession) -> list[tuple[User, list[str]]]:
    users = (await session.execute(select(User).order_by(User.name))).scalars().all()
    contacts = (await session.execute(select(UserContact))).scalars().all()
    by_user: dict[UUID, list[str]] = {}
    for contact in contacts:
        by_user.setdefault(contact.user_id, []).append(contact.value)
    return [(user, by_user.get(user.id, [])) for user in users]


async def _learned_rules(session: AsyncSession) -> list[LearnedRule]:
    rules = (await session.execute(select(ZenMoneyMatchRule))).scalars().all()
    return [LearnedRule(rule.kind, rule.pattern, rule.user_id) for rule in rules]


def _sender_text(transaction: ZenMoneyTransaction) -> str:
    return " ".join(
        value
        for value in (transaction.payee, transaction.original_payee, transaction.comment)
        if value
    )


async def _remember_match(
    session: AsyncSession, transaction: ZenMoneyTransaction, user_id: UUID
) -> None:
    sender = _sender_text(transaction)
    phone = normalize_phone(sender)
    kind = "phone" if phone else "name"
    source = phone or normalize_text(
        transaction.original_payee or transaction.payee or transaction.comment
    )
    if not source:
        return
    rule = await session.scalar(
        select(ZenMoneyMatchRule).where(
            ZenMoneyMatchRule.kind == kind, ZenMoneyMatchRule.pattern == source
        )
    )
    if rule is None:
        session.add(ZenMoneyMatchRule(id=uuid.uuid4(), kind=kind, pattern=source, user_id=user_id))
    else:
        rule.user_id = user_id
    await session.flush()


async def _rematch_pending(session: AsyncSession, account_id: str) -> None:
    users = await _users_with_contacts(session)
    blacklist = list((await session.execute(select(ZenMoneyBlacklistEntry.pattern))).scalars())
    learned_rules = await _learned_rules(session)
    transactions = (
        await session.execute(
            select(ZenMoneyTransaction).where(
                ZenMoneyTransaction.account_id == account_id,
                ZenMoneyTransaction.payment_id.is_(None),
                ZenMoneyTransaction.decision_source == "automatic",
                ZenMoneyTransaction.deleted.is_(False),
                ZenMoneyTransaction.hold.is_(False),
            )
        )
    ).scalars()
    for transaction in transactions:
        match = match_sender(_sender_text(transaction), users, blacklist, learned_rules)
        transaction.status = match.status
        transaction.user_id = match.user_id
        transaction.match_reason = match.reason


async def _deactivate_payment(session: AsyncSession, transaction: ZenMoneyTransaction) -> None:
    if transaction.payment_id:
        payment = await session.get(Payment, transaction.payment_id)
        if payment:
            payment.included_in_balance = False


async def _upsert_payment(
    session: AsyncSession,
    transaction: ZenMoneyTransaction,
    configured: ZenMoneySettings,
    *,
    create_if_missing: bool,
) -> bool:
    if transaction.user_id is None or transaction.hold or transaction.deleted:
        await _deactivate_payment(session, transaction)
        return False
    amount = round(transaction.amount)
    if abs(transaction.amount - amount) > 0.001:
        transaction.status = "review"
        transaction.user_id = None
        transaction.match_reason = "amount is not an integer"
        return False
    payment = await session.get(Payment, transaction.payment_id) if transaction.payment_id else None
    if payment is None:
        linked_ids = select(ZenMoneyTransaction.payment_id).where(
            ZenMoneyTransaction.payment_id.is_not(None)
        )
        candidates = (
            (
                await session.execute(
                    select(Payment).where(
                        Payment.user_id == transaction.user_id,
                        Payment.payment_type_id == configured.payment_type_id,
                        Payment.payment_date == transaction.transaction_date,
                        Payment.sum == amount,
                        Payment.id.not_in(linked_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(candidates) == 1:
            payment = candidates[0]
        elif len(candidates) > 1:
            transaction.status = "review"
            transaction.user_id = None
            transaction.match_reason = "multiple existing payments match"
            return False
        else:
            if not create_if_missing:
                return False
            max_position = await session.scalar(select(func.max(Payment.legacy_position)))
            payment = Payment(
                id=uuid.uuid4(),
                legacy_position=(max_position if max_position is not None else -1) + 1,
                source_key=f"zenmoney:{transaction.zenmoney_id}",
                user_id=transaction.user_id,
                payment_type_id=configured.payment_type_id,
                payment_date=transaction.transaction_date,
                payment_date_raw=transaction.transaction_date.strftime("%d.%m.%Y"),
                registration_date_raw=None,
                registration_date_parsed=None,
                sum=amount,
                comment=transaction.comment or transaction.payee or "",
                included_in_balance=True,
            )
            session.add(payment)
            await session.flush()
        transaction.payment_id = payment.id
    payment.user_id = transaction.user_id
    payment.payment_type_id = configured.payment_type_id
    payment.payment_date = transaction.transaction_date
    payment.payment_date_raw = transaction.transaction_date.strftime("%d.%m.%Y")
    payment.sum = amount
    payment.comment = transaction.comment or transaction.payee or ""
    payment.included_in_balance = True
    return True


def is_selected_account_income(item: dict[str, Any], account_id: str) -> bool:
    """Accept external income and exclude transfers between the user's own accounts."""
    outcome_account = item.get("outcomeAccount")
    return (
        item.get("incomeAccount") == account_id
        and outcome_account in {None, account_id}
        and isinstance(item.get("income"), (int, float))
        and item.get("income", 0) > 0
    )


def should_process_existing_transaction(
    transaction: ZenMoneyTransaction, selected_account_id: str, *, incoming: bool
) -> bool:
    """Keep transactions from other accounts untouched when the selection changes."""
    return incoming or transaction.account_id == selected_account_id


async def sync(session: AsyncSession, settings: Settings) -> ZenMoneySyncResponse:
    configured = await session.scalar(
        select(ZenMoneySettings).where(ZenMoneySettings.id == 1).with_for_update()
    )
    if configured is None:
        raise ZenMoneyError("ZenMoney is not configured.", code="not_configured")
    diff = await request_diff(
        decrypt_token(configured.access_token_ciphertext, settings), configured.server_timestamp
    )
    users = await _users_with_contacts(session)
    blacklist = list((await session.execute(select(ZenMoneyBlacklistEntry.pattern))).scalars())
    learned_rules = await _learned_rules(session)
    counts = {"created": 0, "updated": 0, "matched": 0, "review": 0, "blacklisted": 0}
    transactions = [item for item in diff.get("transaction", []) if isinstance(item, dict)]
    for item in transactions:
        external_id = str(item.get("id") or "")
        if not external_id:
            continue
        transaction = await session.scalar(
            select(ZenMoneyTransaction).where(ZenMoneyTransaction.zenmoney_id == external_id)
        )
        incoming = is_selected_account_income(item, configured.account_id)
        if transaction is not None and not should_process_existing_transaction(
            transaction, configured.account_id, incoming=incoming
        ):
            continue
        if transaction is None and not incoming:
            continue
        if transaction is None:
            transaction = ZenMoneyTransaction(
                id=uuid.uuid5(_TRANSACTION_NAMESPACE, external_id),
                zenmoney_id=external_id,
                account_id=configured.account_id,
                status="review",
                decision_source="automatic",
                changed=0,
                transaction_date=date.today(),
                amount=0,
            )
            session.add(transaction)
            counts["created"] += 1
        else:
            counts["updated"] += 1
        transaction.account_id = configured.account_id
        transaction.changed = int(item.get("changed") or 0)
        try:
            transaction.transaction_date = date.fromisoformat(str(item.get("date")))
        except ValueError:
            transaction.transaction_date = date.today()
        transaction.amount = float(item.get("income") or transaction.amount)
        transaction.payee = item.get("payee")
        transaction.original_payee = item.get("originalPayee")
        transaction.comment = item.get("comment")
        transaction.hold = bool(item.get("hold", False))
        transaction.deleted = bool(item.get("deleted", False)) or not incoming
        if transaction.deleted:
            transaction.status = "rejected"
            transaction.match_reason = (
                "internal transfer"
                if item.get("incomeAccount") == configured.account_id
                and item.get("outcomeAccount") not in {None, configured.account_id}
                else "deleted or moved away from selected account"
            )
            transaction.user_id = None
        elif transaction.decision_source == "manual" and transaction.user_id is None:
            transaction.status = "rejected"
            transaction.match_reason = "manually rejected"
        elif transaction.hold:
            transaction.status = "review"
            transaction.match_reason = "transaction is on hold"
        elif transaction.decision_source == "manual":
            if transaction.user_id is not None:
                transaction.status = "matched"
                transaction.match_reason = "manual assignment"
        else:
            match = match_sender(_sender_text(transaction), users, blacklist, learned_rules)
            transaction.status = match.status
            transaction.user_id = match.user_id
            transaction.match_reason = match.reason
        if transaction.status == "matched":
            await _upsert_payment(session, transaction, configured, create_if_missing=False)
            counts["matched"] += 1
        else:
            await _deactivate_payment(session, transaction)
            counts[transaction.status if transaction.status in counts else "review"] += 1
    for item in diff.get("deletion", []):
        if not isinstance(item, dict) or str(item.get("object", "")).casefold() != "transaction":
            continue
        transaction = await session.scalar(
            select(ZenMoneyTransaction).where(
                ZenMoneyTransaction.zenmoney_id == str(item.get("id") or ""),
                ZenMoneyTransaction.account_id == configured.account_id,
            )
        )
        if transaction is None:
            continue
        transaction.deleted = True
        transaction.status = "rejected"
        transaction.user_id = None
        transaction.match_reason = "deleted in ZenMoney"
        await _deactivate_payment(session, transaction)
        counts["updated"] += 1
    configured.server_timestamp = diff["serverTimestamp"]
    configured.last_sync_at = datetime.now(UTC)
    await session.commit()
    return ZenMoneySyncResponse(
        received=len(transactions), server_timestamp=configured.server_timestamp, **counts
    )


async def approve_all_matched(session: AsyncSession) -> ZenMoneyBulkApproveResponse:
    configured = await session.get(ZenMoneySettings, 1)
    if configured is None:
        raise ZenMoneyError("ZenMoney is not configured.", code="not_configured")
    transactions = (
        await session.execute(
            select(ZenMoneyTransaction)
            .where(
                ZenMoneyTransaction.account_id == configured.account_id,
                ZenMoneyTransaction.status == "matched",
                ZenMoneyTransaction.user_id.is_not(None),
                ZenMoneyTransaction.payment_id.is_(None),
                ZenMoneyTransaction.hold.is_(False),
                ZenMoneyTransaction.deleted.is_(False),
            )
            .order_by(ZenMoneyTransaction.transaction_date, ZenMoneyTransaction.id)
        )
    ).scalars()
    approved = 0
    skipped = 0
    for transaction in transactions:
        if await _upsert_payment(session, transaction, configured, create_if_missing=True):
            approved += 1
        else:
            skipped += 1
    await session.commit()
    return ZenMoneyBulkApproveResponse(approved=approved, skipped=skipped)


async def list_transactions(
    session: AsyncSession, *, include_blacklisted: bool, status: str | None
) -> list[ZenMoneyTransactionResponse]:
    query = (
        select(ZenMoneyTransaction, User.name)
        .outerjoin(User, User.id == ZenMoneyTransaction.user_id)
        .order_by(ZenMoneyTransaction.transaction_date.desc(), ZenMoneyTransaction.id)
    )
    configured = await session.get(ZenMoneySettings, 1)
    if configured is None:
        return []
    query = query.where(ZenMoneyTransaction.account_id == configured.account_id)
    if not include_blacklisted:
        query = query.where(ZenMoneyTransaction.status != "blacklisted")
    if status:
        query = query.where(ZenMoneyTransaction.status == status)
    rows = (await session.execute(query)).all()
    return [
        ZenMoneyTransactionResponse(
            id=item.id,
            transaction_date=item.transaction_date,
            amount=item.amount,
            payee=item.payee,
            original_payee=item.original_payee,
            comment=item.comment,
            hold=item.hold,
            deleted=item.deleted,
            status=item.status,  # type: ignore[arg-type]
            decision_source=item.decision_source,  # type: ignore[arg-type]
            match_reason=item.match_reason,
            user_id=item.user_id,
            user_name=user_name,
            payment_id=item.payment_id,
        )
        for item, user_name in rows
    ]


async def decide(
    session: AsyncSession,
    transaction_id: UUID,
    action: str,
    user_id: UUID | None,
) -> ZenMoneyTransactionResponse:
    transaction = await session.get(ZenMoneyTransaction, transaction_id)
    configured = await session.get(ZenMoneySettings, 1)
    if transaction is None or configured is None:
        raise ZenMoneyError(
            "Transaction was not found.", code="transaction_not_found", status_code=404
        )
    if action == "assign":
        if transaction.deleted or transaction.hold:
            raise ZenMoneyError(
                "A deleted or pending transaction cannot be assigned.",
                code="transaction_not_settled",
                status_code=409,
            )
        user = await session.get(User, user_id)
        if user is None:
            raise ZenMoneyError("User was not found.", code="user_not_found", status_code=404)
        transaction.status = "matched"
        transaction.user_id = user.id
        transaction.decision_source = "manual"
        transaction.match_reason = "manual assignment"
        await _remember_match(session, transaction, user.id)
        await _rematch_pending(session, configured.account_id)
        if transaction.payment_id is not None:
            await _upsert_payment(session, transaction, configured, create_if_missing=False)
    elif action == "approve":
        if transaction.status != "matched" or transaction.user_id is None:
            raise ZenMoneyError(
                "Match the transaction to a participant before approval.",
                code="transaction_not_matched",
                status_code=409,
            )
        await _upsert_payment(session, transaction, configured, create_if_missing=True)
    elif action == "reject":
        transaction.status = "rejected"
        transaction.user_id = None
        transaction.decision_source = "manual"
        transaction.match_reason = "manually rejected"
        await _deactivate_payment(session, transaction)
    else:
        transaction.decision_source = "automatic"
        if transaction.deleted:
            transaction.status = "rejected"
            transaction.user_id = None
            transaction.match_reason = "transaction is deleted"
            await _deactivate_payment(session, transaction)
            await session.commit()
            values = await list_transactions(session, include_blacklisted=True, status=None)
            return next(value for value in values if value.id == transaction_id)
        if transaction.hold:
            transaction.status = "review"
            transaction.user_id = None
            transaction.match_reason = "transaction is on hold"
            await _deactivate_payment(session, transaction)
            await session.commit()
            values = await list_transactions(session, include_blacklisted=True, status=None)
            return next(value for value in values if value.id == transaction_id)
        users = await _users_with_contacts(session)
        blacklist = list((await session.execute(select(ZenMoneyBlacklistEntry.pattern))).scalars())
        learned_rules = await _learned_rules(session)
        match = match_sender(_sender_text(transaction), users, blacklist, learned_rules)
        transaction.status, transaction.user_id, transaction.match_reason = (
            match.status,
            match.user_id,
            match.reason,
        )
        if transaction.status == "matched":
            if transaction.payment_id is not None:
                await _upsert_payment(session, transaction, configured, create_if_missing=False)
        else:
            await _deactivate_payment(session, transaction)
    await session.commit()
    values = await list_transactions(session, include_blacklisted=True, status=None)
    return next(value for value in values if value.id == transaction_id)
