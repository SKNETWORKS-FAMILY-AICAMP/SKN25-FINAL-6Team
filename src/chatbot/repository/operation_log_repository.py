from __future__ import annotations

from typing import Any

from chatbot.repository.base import read_response, safe_read


def _db_context() -> tuple[Any, Any]:
    from psycopg.rows import dict_row
    from src.common.db.connection import db_connection

    return db_connection, dict_row


def read_payments_by_account(account_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        db_connection, dict_row = _db_context()
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        payment_id,
                        account_id,
                        product_name,
                        product_type,
                        amount,
                        currency,
                        payment_method,
                        payment_status,
                        transaction_id,
                        paid_at
                    FROM payments
                    WHERE account_id = %s
                    ORDER BY paid_at DESC NULLS LAST
                    LIMIT 10
                    """,
                    (account_id,),
                )
                return read_response([dict(row) for row in cur.fetchall()])

    return safe_read(operation="read_payments", reader=_read)


def read_refunds_by_payment(payment_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        db_connection, dict_row = _db_context()
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        refund_id,
                        payment_id,
                        refund_status,
                        refund_reason,
                        requested_at,
                        processed_at
                    FROM refunds
                    WHERE payment_id = %s
                    ORDER BY requested_at DESC NULLS LAST
                    LIMIT 10
                    """,
                    (payment_id,),
                )
                return read_response([dict(row) for row in cur.fetchall()])

    return safe_read(operation="read_refunds", reader=_read)


def read_item_delivery_logs_by_account(account_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        db_connection, dict_row = _db_context()
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        delivery_id,
                        payment_id,
                        account_id,
                        source_type,
                        item_name,
                        quantity,
                        delivery_status,
                        expected_at,
                        delivered_at
                    FROM item_delivery_logs
                    WHERE account_id = %s
                    ORDER BY expected_at DESC NULLS LAST, delivered_at DESC NULLS LAST
                    LIMIT 10
                    """,
                    (account_id,),
                )
                return read_response([dict(row) for row in cur.fetchall()])

    return safe_read(operation="read_item_delivery_logs", reader=_read)


def read_gacha_logs_by_account(account_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        db_connection, dict_row = _db_context()
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        gacha_id,
                        account_id,
                        banner_name,
                        item_name,
                        item_type,
                        rarity,
                        pity_count,
                        pulled_at
                    FROM gacha_logs
                    WHERE account_id = %s
                    ORDER BY pulled_at DESC NULLS LAST
                    LIMIT 10
                    """,
                    (account_id,),
                )
                return read_response([dict(row) for row in cur.fetchall()])

    return safe_read(operation="read_gacha_logs", reader=_read)
