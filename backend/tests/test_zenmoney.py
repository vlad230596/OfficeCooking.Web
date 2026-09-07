from types import SimpleNamespace
from uuid import uuid4

from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.config import Settings
from app.models import User
from app.services.zenmoney import (
    LearnedRule,
    decrypt_token,
    encrypt_token,
    is_selected_account_income,
    match_sender,
    should_process_existing_transaction,
)


def user(name: str) -> User:
    return User(id=uuid4(), name=name)


def test_access_token_is_encrypted_and_can_only_be_read_with_server_key() -> None:
    settings = Settings(zenmoney_encryption_key=Fernet.generate_key().decode())
    ciphertext = encrypt_token("secret-access-token", settings)

    assert "secret-access-token" not in ciphertext
    assert decrypt_token(ciphertext, settings) == "secret-access-token"


def test_production_can_derive_token_key_from_database_password() -> None:
    settings = Settings(
        environment="production",
        session_cookie_secure=True,
        database_url="postgresql+asyncpg://officecook:secret@postgres/officecook",
        database_password=SecretStr("a-long-production-database-password"),
        zenmoney_encryption_key=None,
    )
    ciphertext = encrypt_token("production-token", settings)

    assert "production-token" not in ciphertext
    assert decrypt_token(ciphertext, settings) == "production-token"


def test_blacklist_wins_before_user_matching() -> None:
    person = user("Иван Иванов")

    result = match_sender(
        "Иван Иванов +7 999 111-22-33", [(person, ["+79991112233"])], ["Иван Иванов"]
    )

    assert result.status == "blacklisted"
    assert result.user_id is None


def test_unique_phone_and_reversed_legacy_name_are_matched() -> None:
    person = user("Иван Иванов")

    by_phone = match_sender("Перевод +7 (999) 111-22-33", [(person, ["+79991112233"])], [])
    by_name = match_sender("Иванов Иван Сергеевич", [(person, [])], [])

    assert (by_phone.status, by_phone.user_id, by_phone.reason) == (
        "matched",
        person.id,
        "phone",
    )
    assert (by_name.status, by_name.user_id, by_name.reason) == ("matched", person.id, "name")


def test_short_name_and_patronymic_format_follow_legacy_alfa_rules() -> None:
    person = user("Евгений Королёв")

    abbreviated = match_sender("Евгений К.", [(person, [])], [])
    bank_order = match_sender("Королев Евгений Сергеевич", [(person, [])], [])

    assert (abbreviated.status, abbreviated.user_id, abbreviated.reason) == (
        "matched",
        person.id,
        "name",
    )
    assert (bank_order.status, bank_order.user_id, bank_order.reason) == (
        "matched",
        person.id,
        "name",
    )


def test_learned_rule_is_explicit_and_wins_before_ordinary_matching() -> None:
    person = user("Александр Петров")
    rule = LearnedRule("name", "александр п", person.id)

    result = match_sender("Александр П.", [(person, [])], [], [rule])

    assert (result.status, result.user_id, result.reason) == (
        "matched",
        person.id,
        "learned name",
    )


def test_ambiguous_contact_requires_manual_review() -> None:
    first = user("Первый")
    second = user("Второй")

    result = match_sender(
        "+79991112233", [(first, ["+79991112233"]), (second, ["+79991112233"])], []
    )

    assert result.status == "review"
    assert result.reason == "ambiguous contact"


def test_selected_account_income_excludes_internal_transfers() -> None:
    account_id = "selected"

    assert is_selected_account_income(
        {"incomeAccount": account_id, "outcomeAccount": account_id, "income": 500},
        account_id,
    )
    assert is_selected_account_income(
        {"incomeAccount": account_id, "outcomeAccount": None, "income": 500},
        account_id,
    )
    assert not is_selected_account_income(
        {"incomeAccount": account_id, "outcomeAccount": "savings", "income": 500},
        account_id,
    )


def test_account_switch_does_not_process_transactions_from_previous_account() -> None:
    transaction = SimpleNamespace(account_id="previous")

    assert not should_process_existing_transaction(
        transaction,
        "selected",
        incoming=False,  # type: ignore[arg-type]
    )
    assert should_process_existing_transaction(
        transaction,
        "selected",
        incoming=True,  # type: ignore[arg-type]
    )
