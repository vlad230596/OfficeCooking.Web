"""Add default T-Bank system-operation filters.

Revision ID: 0008_tbank_system_filters
Revises: 0007_account_blacklists
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_tbank_system_filters"
down_revision: str | Sequence[str] | None = "0007_account_blacklists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pg_text(value: str) -> str:
    """Render UTF-8 text while keeping offline migration output ASCII-only on Windows."""

    return f"convert_from(decode('{value.encode().hex()}', 'hex'), 'UTF8')"


def upgrade() -> None:
    cashback = _pg_text("Зачисление кэшбэка")
    city = _pg_text("Супермаркеты в Городе")
    empty = _pg_text("Операции без отправителя")
    tbank = _pg_text("Т-Банк")
    op.execute(
        f"""
        INSERT INTO zenmoney_blacklist_entries (id, account_id, pattern)
        SELECT (
            substr(hash, 1, 8) || '-' || substr(hash, 9, 4) || '-' ||
            substr(hash, 13, 4) || '-' || substr(hash, 17, 4) || '-' ||
            substr(hash, 21, 12)
        )::uuid, account_id, pattern
        FROM (
            SELECT config.account_id, defaults.pattern,
                   md5(config.account_id || defaults.pattern) AS hash
            FROM zenmoney_account_configs config
            CROSS JOIN (VALUES
                ({cashback}),
                ({city}),
                ({empty})
            ) AS defaults(pattern)
            WHERE lower(config.account_title) LIKE '%' || lower({tbank}) || '%'
        ) generated
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        f"""
        UPDATE zenmoney_transactions zt
        SET status = 'blacklisted', user_id = NULL,
            match_reason = CASE
                WHEN btrim(concat_ws(' ', zt.payee, zt.original_payee, zt.comment)) = ''
                    THEN 'blacklist: ' || {empty}
                WHEN lower(concat_ws(' ', zt.payee, zt.original_payee, zt.comment))
                    LIKE '%' || lower({cashback}) || '%'
                    THEN 'blacklist: ' || {cashback}
                ELSE 'blacklist: ' || {city}
            END
        FROM zenmoney_account_configs config
        WHERE zt.account_id = config.account_id
          AND lower(config.account_title) LIKE '%' || lower({tbank}) || '%'
          AND zt.payment_id IS NULL
          AND zt.decision_source = 'automatic'
          AND (
              btrim(concat_ws(' ', zt.payee, zt.original_payee, zt.comment)) = ''
              OR lower(concat_ws(' ', zt.payee, zt.original_payee, zt.comment))
                 LIKE '%' || lower({cashback}) || '%'
              OR lower(concat_ws(' ', zt.payee, zt.original_payee, zt.comment))
                 LIKE '%' || lower({city}) || '%'
          )
        """
    )


def downgrade() -> None:
    cashback = _pg_text("Зачисление кэшбэка")
    city = _pg_text("Супермаркеты в Городе")
    empty = _pg_text("Операции без отправителя")
    tbank = _pg_text("Т-Банк")
    op.execute(
        f"""
        UPDATE zenmoney_transactions zt
        SET status = 'review', match_reason = 'no unique user match'
        FROM zenmoney_account_configs config
        WHERE zt.account_id = config.account_id
          AND lower(config.account_title) LIKE '%' || lower({tbank}) || '%'
          AND zt.payment_id IS NULL
          AND zt.match_reason IN (
              'blacklist: ' || {cashback},
              'blacklist: ' || {city},
              'blacklist: ' || {empty}
          )
        """
    )
    op.execute(
        f"""
        DELETE FROM zenmoney_blacklist_entries entry
        USING zenmoney_account_configs config
        WHERE entry.account_id = config.account_id
          AND lower(config.account_title) LIKE '%' || lower({tbank}) || '%'
          AND entry.pattern IN (
              {cashback},
              {city},
              {empty}
          )
        """
    )
