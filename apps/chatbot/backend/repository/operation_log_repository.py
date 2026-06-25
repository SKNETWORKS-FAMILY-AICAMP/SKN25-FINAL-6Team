from __future__ import annotations

import json
import re
from typing import Any

from repository.base import read_response, safe_read


PAYMENT_CONTEXT_LIMIT = 20
# 한 글자 조사는 검색 잡음을 키우므로 2자 이상 토큰만 payment context matching에 사용한다.
PAYMENT_SEARCH_MIN_TOKEN_CHARS = 2
# ILIKE 조건이 과도하게 늘어나지 않도록 사용자 질문에서 최대 12개 토큰만 검색 패턴으로 쓴다.
PAYMENT_SEARCH_MAX_PATTERNS = 12


# operation log 조회는 여러 함수에서 같은 DB connection/cursor 패턴을 사용한다.
def _db_context() -> tuple[Any, Any]:
    from psycopg.rows import dict_row
    from common.db.connection import db_connection

    return db_connection, dict_row


def _payment_search_patterns(query_text: str | None) -> list[str]:
    text = str(query_text or "")
    terms = [
        token
        for token in re.findall(r"[0-9A-Za-z가-힣]+", text)
        if len(token) >= PAYMENT_SEARCH_MIN_TOKEN_CHARS
    ]
    return [f"%{term}%" for term in list(dict.fromkeys(terms))[:PAYMENT_SEARCH_MAX_PATTERNS]]


# 로그인 사용자 소유 계정의 아이템 지급 로그만 조회한다.
def read_item_delivery_logs_by_account(*, user_id: int, account_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        db_connection, dict_row = _db_context()
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        delivery_id,
                        payment_id,
                        d.account_id,
                        source_type,
                        item_name,
                        quantity,
                        delivery_status,
                        expected_at,
                        delivered_at
                    FROM item_delivery_logs d
                    JOIN game_accounts a ON a.account_id = d.account_id
                    WHERE a.user_id = %s
                        AND d.account_id = %s
                    ORDER BY expected_at DESC NULLS LAST, delivered_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    (user_id, account_id, PAYMENT_CONTEXT_LIMIT),
                )
                return read_response([dict(row) for row in cur.fetchall()])

    return safe_read(operation="read_item_delivery_logs", reader=_read)


# 로그인 사용자 소유 계정의 가챠/뽑기 로그만 조회한다.
def read_gacha_logs_by_account(*, user_id: int, account_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        db_connection, dict_row = _db_context()
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        gacha_id,
                        g.account_id,
                        banner_name,
                        item_name,
                        item_type,
                        rarity,
                        pity_count,
                        pulled_at
                    FROM gacha_logs g
                    JOIN game_accounts a ON a.account_id = g.account_id
                    WHERE a.user_id = %s
                        AND g.account_id = %s
                    ORDER BY pulled_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    (user_id, account_id, PAYMENT_CONTEXT_LIMIT),
                )
                return read_response([dict(row) for row in cur.fetchall()])

    return safe_read(operation="read_gacha_logs", reader=_read)


# payment agent가 한 번에 사용할 수 있도록 결제/환불/지급/가챠 context를 사용자 소유 범위로 묶는다.
def collect_payment_context_by_user(
    user_id: int,
    account_id: int | None = None,
    query_text: str | None = None,
) -> dict[str, Any]:
    """Read payment-related evidence only from accounts owned by the logged-in user."""

    def _read() -> dict[str, Any]:
        db_connection, dict_row = _db_context()
        account_filter = "AND (%s IS NULL OR a.account_id = %s)"
        account_params = (account_id, account_id)
        search_patterns = _payment_search_patterns(query_text)

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
                    LIMIT %s
                    """,
                    (user_id, *account_params, PAYMENT_CONTEXT_LIMIT),
                )
                accounts = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    f"""
                    WITH evidence AS (
                        SELECT
                            'payments' AS record_type,
                            p.paid_at AS sort_at,
                            concat_ws(
                                ' ',
                                p.transaction_id,
                                p.product_name,
                                p.product_type,
                                p.payment_method,
                                p.payment_status
                            ) AS search_text,
                            jsonb_build_object(
                                'payment_id', p.payment_id,
                                'account_id', p.account_id,
                                'product_name', p.product_name,
                                'product_type', p.product_type,
                                'amount', p.amount,
                                'currency', p.currency,
                                'payment_method', p.payment_method,
                                'payment_status', p.payment_status,
                                'transaction_id', p.transaction_id,
                                'paid_at', p.paid_at
                            ) AS payload
                        FROM payments p
                        JOIN game_accounts a ON a.account_id = p.account_id
                        WHERE a.user_id = %s
                            {account_filter}

                        UNION ALL

                        SELECT
                            'refunds' AS record_type,
                            r.requested_at AS sort_at,
                            concat_ws(
                                ' ',
                                p.transaction_id,
                                p.product_name,
                                p.payment_status,
                                r.refund_status,
                                r.refund_reason
                            ) AS search_text,
                            jsonb_build_object(
                                'refund_id', r.refund_id,
                                'payment_id', r.payment_id,
                                'account_id', p.account_id,
                                'product_name', p.product_name,
                                'payment_status', p.payment_status,
                                'paid_at', p.paid_at,
                                'refund_status', r.refund_status,
                                'refund_reason', r.refund_reason,
                                'requested_at', r.requested_at,
                                'processed_at', r.processed_at
                            ) AS payload
                        FROM refunds r
                        JOIN payments p ON p.payment_id = r.payment_id
                        JOIN game_accounts a ON a.account_id = p.account_id
                        WHERE a.user_id = %s
                            {account_filter}

                        UNION ALL

                        SELECT
                            'item_delivery_logs' AS record_type,
                            COALESCE(d.expected_at, d.delivered_at) AS sort_at,
                            concat_ws(
                                ' ',
                                p.transaction_id,
                                p.product_name,
                                d.source_type,
                                d.item_name,
                                d.delivery_status
                            ) AS search_text,
                            jsonb_build_object(
                                'delivery_id', d.delivery_id,
                                'payment_id', d.payment_id,
                                'account_id', d.account_id,
                                'source_type', d.source_type,
                                'item_name', d.item_name,
                                'quantity', d.quantity,
                                'delivery_status', d.delivery_status,
                                'expected_at', d.expected_at,
                                'delivered_at', d.delivered_at
                            ) AS payload
                        FROM item_delivery_logs d
                        JOIN game_accounts a ON a.account_id = d.account_id
                        LEFT JOIN payments p ON p.payment_id = d.payment_id
                        WHERE a.user_id = %s
                            {account_filter}

                        UNION ALL

                        SELECT
                            'gacha_logs' AS record_type,
                            g.pulled_at AS sort_at,
                            concat_ws(
                                ' ',
                                g.banner_name,
                                g.item_name,
                                g.item_type,
                                g.rarity
                            ) AS search_text,
                            jsonb_build_object(
                                'gacha_id', g.gacha_id,
                                'account_id', g.account_id,
                                'banner_name', g.banner_name,
                                'item_name', g.item_name,
                                'item_type', g.item_type,
                                'rarity', g.rarity,
                                'pity_count', g.pity_count,
                                'pulled_at', g.pulled_at
                            ) AS payload
                        FROM gacha_logs g
                        JOIN game_accounts a ON a.account_id = g.account_id
                        WHERE a.user_id = %s
                            {account_filter}
                    ),
                    scored AS (
                        SELECT
                            record_type,
                            payload,
                            sort_at,
                            (
                                SELECT count(*)
                                FROM unnest(%s::text[]) AS pattern
                                WHERE search_text ILIKE pattern
                            ) AS relevance_score
                        FROM evidence
                    ),
                    ranked AS (
                        SELECT
                            record_type,
                            payload,
                            row_number() OVER (
                                PARTITION BY record_type
                                ORDER BY relevance_score DESC, sort_at DESC NULLS LAST
                            ) AS record_rank
                        FROM scored
                    )
                    SELECT record_type, payload
                    FROM ranked
                    WHERE record_rank <= %s
                    ORDER BY record_type, record_rank
                    """,
                    (
                        user_id,
                        *account_params,
                        user_id,
                        *account_params,
                        user_id,
                        *account_params,
                        user_id,
                        *account_params,
                        search_patterns,
                        PAYMENT_CONTEXT_LIMIT,
                    ),
                )
                evidence_rows = [dict(row) for row in cur.fetchall()]

                grouped_rows: dict[str, list[dict[str, Any]]] = {
                    "payments": [],
                    "refunds": [],
                    "item_delivery_logs": [],
                    "gacha_logs": [],
                }
                for row in evidence_rows:
                    record_type = str(row.get("record_type") or "")
                    payload = row.get("payload")
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    if record_type in grouped_rows and isinstance(payload, dict):
                        grouped_rows[record_type].append(payload)

                payments = grouped_rows["payments"]
                refunds = grouped_rows["refunds"]
                item_delivery_logs = grouped_rows["item_delivery_logs"]
                gacha_logs = grouped_rows["gacha_logs"]

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
