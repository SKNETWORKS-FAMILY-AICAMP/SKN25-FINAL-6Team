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


def collect_payment_context_by_user(user_id: int, account_id: int | None = None) -> dict[str, Any]:
    """Read payment-related evidence only from accounts owned by the logged-in user."""

    def _read() -> dict[str, Any]:
        db_connection, dict_row = _db_context()
        account_filter = "AND (%s IS NULL OR a.account_id = %s)"
        account_params = (account_id, account_id)

        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    SELECT
                        a.account_id,
                        a.user_id,
                        a.game_name,
                        a.uid,
                        a.server_region,
                        a.account_status
                    FROM game_accounts a
                    WHERE a.user_id = %s
                        {account_filter}
                    ORDER BY a.account_id
                    LIMIT 10
                    """,
                    (user_id, *account_params),
                )
                accounts = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    f"""
                    SELECT
                        p.payment_id,
                        p.account_id,
                        p.product_name,
                        p.product_type,
                        p.amount,
                        p.currency,
                        p.payment_method,
                        p.payment_status,
                        p.transaction_id,
                        p.paid_at
                    FROM payments p
                    JOIN game_accounts a ON a.account_id = p.account_id
                    WHERE a.user_id = %s
                        {account_filter}
                    ORDER BY p.paid_at DESC NULLS LAST
                    LIMIT 10
                    """,
                    (user_id, *account_params),
                )
                payments = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    f"""
                    SELECT
                        r.refund_id,
                        r.payment_id,
                        p.account_id,
                        p.product_name,
                        p.payment_status,
                        p.paid_at,
                        r.refund_status,
                        r.refund_reason,
                        r.requested_at,
                        r.processed_at
                    FROM refunds r
                    JOIN payments p ON p.payment_id = r.payment_id
                    JOIN game_accounts a ON a.account_id = p.account_id
                    WHERE a.user_id = %s
                        {account_filter}
                    ORDER BY r.requested_at DESC NULLS LAST
                    LIMIT 10
                    """,
                    (user_id, *account_params),
                )
                refunds = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    f"""
                    SELECT
                        d.delivery_id,
                        d.payment_id,
                        d.account_id,
                        d.source_type,
                        d.item_name,
                        d.quantity,
                        d.delivery_status,
                        d.expected_at,
                        d.delivered_at
                    FROM item_delivery_logs d
                    JOIN game_accounts a ON a.account_id = d.account_id
                    WHERE a.user_id = %s
                        {account_filter}
                    ORDER BY d.expected_at DESC NULLS LAST, d.delivered_at DESC NULLS LAST
                    LIMIT 10
                    """,
                    (user_id, *account_params),
                )
                item_delivery_logs = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    f"""
                    SELECT
                        g.gacha_id,
                        g.account_id,
                        g.banner_name,
                        g.item_name,
                        g.item_type,
                        g.rarity,
                        g.pity_count,
                        g.pulled_at
                    FROM gacha_logs g
                    JOIN game_accounts a ON a.account_id = g.account_id
                    WHERE a.user_id = %s
                        {account_filter}
                    ORDER BY g.pulled_at DESC NULLS LAST
                    LIMIT 10
                    """,
                    (user_id, *account_params),
                )
                gacha_logs = [dict(row) for row in cur.fetchall()]

        return {
            "status": "ok",
            "user_id": user_id,
            "account_id": account_id,
            "data": {
                "accounts": accounts,
                "payments": payments,
                "refunds": refunds,
                "item_delivery_logs": item_delivery_logs,
                "gacha_logs": gacha_logs,
            },
            "counts": {
                "accounts": len(accounts),
                "payments": len(payments),
                "refunds": len(refunds),
                "item_delivery_logs": len(item_delivery_logs),
                "gacha_logs": len(gacha_logs),
            },
            "count": len(payments) + len(refunds) + len(item_delivery_logs) + len(gacha_logs),
        }

    return safe_read(operation="collect_payment_context", reader=_read)
