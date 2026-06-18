from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection


OUTPUT_PATH = Path(__file__).with_name("routing_target_gold_dataset_live_candidates.json")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def _must_include_for_doc(intent_family: str) -> list[str]:
    mapping = {
        "account_password": [
            "문서에 있는 비밀번호 변경 경로를 안내",
            "계정 설정 또는 통행증 홈페이지 경로를 포함",
        ],
        "latest_notice": [
            "최신 공지 제목을 정확히 안내",
            "최신 기준이라는 점을 명시",
        ],
        "mail_reward": [
            "우편 수령 기간 또는 공지된 수령 조건을 안내",
            "공지에 적힌 기한만 안내",
        ],
    }
    return mapping.get(intent_family, [])


def _must_not_include_for_doc(intent_family: str) -> list[str]:
    mapping = {
        "account_password": [
            "운영자가 비밀번호를 직접 바꿔준다는 표현",
            "무관한 제재나 복구 절차 혼합",
        ],
        "latest_notice": [
            "실제 문서에 없는 공지 제목",
            "계정별 운영 로그 설명",
        ],
        "mail_reward": [
            "공지에 없는 추가 예외나 보상 확정 표현",
            "DB 지급 로그만으로 우편 정책을 단정하는 표현",
        ],
    }
    return mapping.get(intent_family, [])


def _must_include_for_hybrid(intent_family: str) -> list[str]:
    mapping = {
        "payment_delivery_issue": [
            "실제 payment/delivery 상태를 함께 설명",
            "FAQ의 재확인 절차를 포함",
        ],
        "duplicate_payment": [
            "서로 다른 상품 또는 결제 행을 구분",
            "FAQ에 있는 반환/중복 규칙 범위 내에서만 설명",
        ],
        "refund_after_purchase": [
            "실제 환불 상태와 구매 상태를 함께 설명",
            "관련 FAQ의 제한 조건만 안내",
        ],
    }
    return mapping.get(intent_family, [])


def _must_not_include_for_hybrid(intent_family: str) -> list[str]:
    mapping = {
        "payment_delivery_issue": [
            "현재도 미지급이 확정됐다고 단정",
            "환불 완료나 보상 확정 표현",
        ],
        "duplicate_payment": [
            "실패 결제를 성공 결제로 오인",
            "환불 완료 여부를 추정",
        ],
        "refund_after_purchase": [
            "DB에 없는 환불 완료 또는 지급 회수 상태를 생성",
            "문서에 없는 예외 처리 약속",
        ],
    }
    return mapping.get(intent_family, [])


def fetch_doc_only_candidates(limit: int = 12) -> list[dict[str, Any]]:
    sql = """
    WITH classified_tickets AS (
        SELECT
            q.ticket_id,
            q.account_id,
            q.user_id,
            q.raw_query,
            q.inquiry_created_at,
            CASE
                WHEN q.raw_query ILIKE '%%비밀번호%%' OR q.title ILIKE '%%비밀번호%%' THEN 'account_password'
                WHEN q.raw_query ILIKE '%%최근에 나온 공지%%' OR q.raw_query ILIKE '%%최근에 업데이트된 공지%%' OR q.raw_query ILIKE '%%최신 공지%%' THEN 'latest_notice'
                WHEN q.raw_query ILIKE '%%우편%%' OR q.raw_query ILIKE '%%우편함%%' OR q.raw_query ILIKE '%%보상%%' THEN 'mail_reward'
                ELSE NULL
            END AS intent_family
        FROM qa_ticket q
    ),
    doc_family_map AS (
        SELECT
            d.documents_id,
            d.source_type,
            d.category,
            d.title,
            c.chunk_id,
            c.chunk_order,
            CASE
                WHEN d.documents_id = 'QNA-GSN-3' THEN 'account_password'
                WHEN d.documents_id = 'NVC-NOT-1' THEN 'latest_notice'
                WHEN d.documents_id IN ('NVC-NOT-2', 'NVC-NOT-3') THEN 'mail_reward'
                ELSE NULL
            END AS intent_family
        FROM documents d
        JOIN documents_chunks c ON c.document_id = d.documents_id
    )
    SELECT
        t.ticket_id,
        t.account_id,
        t.user_id,
        t.raw_query,
        t.inquiry_created_at,
        t.intent_family,
        m.documents_id,
        m.source_type,
        m.category,
        m.title,
        m.chunk_id,
        m.chunk_order
    FROM classified_tickets t
    JOIN doc_family_map m ON m.intent_family = t.intent_family
    WHERE t.intent_family IS NOT NULL
    ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC, m.documents_id, m.chunk_order
    LIMIT %s
    """
    grouped: dict[int, dict[str, Any]] = {}
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (limit * 2,))
            for row in cur.fetchall():
                ticket_id = int(row["ticket_id"])
                existing = grouped.get(ticket_id)
                if existing is None:
                    existing = {
                        "ticket_id": ticket_id,
                        "routing_target": "doc_only",
                        "intent_family": row["intent_family"],
                        "ticket": {
                            "account_id": row["account_id"],
                            "user_id": row["user_id"],
                            "created_at": str(row["inquiry_created_at"]),
                            "question": row["raw_query"],
                        },
                        "gold_policy": {"documents": []},
                    }
                    grouped[ticket_id] = existing
                if len(existing["gold_policy"]["documents"]) < 2:
                    existing["gold_policy"]["documents"].append(
                        {
                            "document_id": row["documents_id"],
                            "chunk_id": row["chunk_id"],
                            "source_type": row["source_type"],
                            "category": row["category"],
                            "title": row["title"],
                        }
                    )
    results = []
    for item in grouped.values():
        intent_family = str(item.pop("intent_family"))
        item["gold_policy"]["must_include"] = _must_include_for_doc(intent_family)
        item["gold_policy"]["must_not_include"] = _must_not_include_for_doc(intent_family)
        results.append(item)
    return results[:limit]


def fetch_db_only_candidates(limit: int = 12) -> list[dict[str, Any]]:
    sql = """
    WITH classified_tickets AS (
        SELECT
            q.ticket_id,
            q.account_id,
            q.user_id,
            q.raw_query,
            q.inquiry_created_at,
            CASE
                WHEN q.raw_query ILIKE '%%결제가 안%%' OR q.raw_query ILIKE '%%결제 안%%' OR q.raw_query ILIKE '%%결제 실패%%' THEN 'payment_failed'
                WHEN q.raw_query ILIKE '%%환불%%' THEN 'refund'
                WHEN q.raw_query ILIKE '%%가챠%%' OR q.raw_query ILIKE '%%뽑기%%' OR q.raw_query ILIKE '%%픽뚫%%' OR q.raw_query ILIKE '%%기원%%' THEN 'gacha'
                ELSE NULL
            END AS intent_family
        FROM qa_ticket q
    ),
    latest_payment AS (
        SELECT DISTINCT ON (p.account_id)
            p.account_id,
            p.payment_id,
            p.product_name,
            p.product_type,
            p.amount,
            p.currency,
            p.payment_method,
            p.payment_status,
            p.paid_at
        FROM payments p
        ORDER BY p.account_id, p.paid_at DESC NULLS LAST, p.payment_id DESC
    ),
    latest_refund AS (
        SELECT DISTINCT ON (p.account_id)
            p.account_id,
            r.refund_id,
            r.payment_id,
            r.refund_status,
            r.refund_reason,
            r.requested_at,
            r.processed_at
        FROM payments p
        JOIN refunds r ON r.payment_id = p.payment_id
        ORDER BY p.account_id, r.requested_at DESC NULLS LAST, r.refund_id DESC
    ),
    latest_delivery AS (
        SELECT DISTINCT ON (d.account_id)
            d.account_id,
            d.delivery_id,
            d.payment_id,
            d.item_name,
            d.quantity,
            d.delivery_status,
            d.expected_at,
            d.delivered_at
        FROM item_delivery_logs d
        ORDER BY d.account_id, d.expected_at DESC NULLS LAST, d.delivery_id DESC
    ),
    recent_gacha AS (
        SELECT
            g.account_id,
            jsonb_agg(
                jsonb_build_object(
                    'gacha_id', g.gacha_id,
                    'banner_name', g.banner_name,
                    'item_name', g.item_name,
                    'item_type', g.item_type,
                    'rarity', g.rarity,
                    'pity_count', g.pity_count,
                    'pulled_at', g.pulled_at
                )
                ORDER BY g.pulled_at DESC NULLS LAST, g.gacha_id DESC
            ) FILTER (WHERE g.rarity = '5성') AS recent_5star_gacha
        FROM (
            SELECT
                g.*,
                ROW_NUMBER() OVER (
                    PARTITION BY g.account_id, g.rarity
                    ORDER BY g.pulled_at DESC NULLS LAST, g.gacha_id DESC
                ) AS rarity_rank
            FROM gacha_logs g
        ) g
        WHERE g.rarity_rank <= 3
        GROUP BY g.account_id
    )
    SELECT
        t.ticket_id,
        t.account_id,
        t.user_id,
        t.raw_query,
        t.inquiry_created_at,
        t.intent_family,
        a.account_status,
        a.server_region,
        lp.payment_id,
        lp.product_name,
        lp.product_type,
        lp.amount,
        lp.currency,
        lp.payment_method,
        lp.payment_status,
        lp.paid_at,
        lr.refund_id,
        lr.payment_id AS refund_payment_id,
        lr.refund_status,
        lr.refund_reason,
        lr.requested_at,
        lr.processed_at,
        ld.delivery_id,
        ld.payment_id AS delivery_payment_id,
        ld.item_name,
        ld.quantity,
        ld.delivery_status,
        ld.expected_at,
        ld.delivered_at,
        rg.recent_5star_gacha
    FROM classified_tickets t
    JOIN game_accounts a ON a.account_id = t.account_id
    LEFT JOIN latest_payment lp ON lp.account_id = t.account_id
    LEFT JOIN latest_refund lr ON lr.account_id = t.account_id
    LEFT JOIN latest_delivery ld ON ld.account_id = t.account_id
    LEFT JOIN recent_gacha rg ON rg.account_id = t.account_id
    WHERE t.intent_family IS NOT NULL
    ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
    LIMIT %s
    """
    results = []
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (limit,))
            for row in cur.fetchall():
                results.append(
                    {
                        "ticket_id": row["ticket_id"],
                        "routing_target": "DB_only",
                        "ticket": {
                            "account_id": row["account_id"],
                            "user_id": row["user_id"],
                            "created_at": str(row["inquiry_created_at"]),
                            "question": row["raw_query"],
                        },
                        "gold_facts": {
                            "account": {
                                "account_status": row["account_status"],
                                "server_region": row["server_region"],
                            },
                            "latest_payment": {
                                "payment_id": row["payment_id"],
                                "product_name": row["product_name"],
                                "product_type": row["product_type"],
                                "amount": row["amount"],
                                "currency": row["currency"],
                                "payment_method": row["payment_method"],
                                "payment_status": row["payment_status"],
                                "paid_at": str(row["paid_at"]) if row["paid_at"] else None,
                            },
                            "latest_refund": {
                                "refund_id": row["refund_id"],
                                "payment_id": row["refund_payment_id"],
                                "refund_status": row["refund_status"],
                                "refund_reason": row["refund_reason"],
                                "requested_at": str(row["requested_at"]) if row["requested_at"] else None,
                                "processed_at": str(row["processed_at"]) if row["processed_at"] else None,
                            }
                            if row["refund_id"] is not None
                            else None,
                            "latest_delivery": {
                                "delivery_id": row["delivery_id"],
                                "payment_id": row["delivery_payment_id"],
                                "item_name": row["item_name"],
                                "quantity": row["quantity"],
                                "delivery_status": row["delivery_status"],
                                "expected_at": str(row["expected_at"]) if row["expected_at"] else None,
                                "delivered_at": str(row["delivered_at"]) if row["delivered_at"] else None,
                            }
                            if row["delivery_id"] is not None
                            else None,
                            "recent_5star_gacha": row["recent_5star_gacha"],
                        },
                        "must_include": [
                            "DB에서 확인되는 최신 상태만 설명",
                            "없는 처리 결과를 생성하지 않음",
                        ],
                        "must_not_include": [
                            "로그에 없는 결제/환불/지급 상태 생성",
                            "가챠 확률 오류를 단정",
                        ],
                    }
                )
    return results


def fetch_hybrid_candidates(limit: int = 12) -> list[dict[str, Any]]:
    sql = """
    WITH classified_tickets AS (
        SELECT
            q.ticket_id,
            q.account_id,
            q.user_id,
            q.raw_query,
            q.inquiry_created_at,
            CASE
                WHEN q.raw_query ILIKE '%%로드되지%%' OR q.raw_query ILIKE '%%지급되지%%' OR q.raw_query ILIKE '%%미지급%%' OR q.raw_query ILIKE '%%상품이 로드%%' THEN 'payment_delivery_issue'
                WHEN q.raw_query ILIKE '%%중복결제%%' OR q.raw_query ILIKE '%%중복 결제%%' THEN 'duplicate_payment'
                WHEN q.raw_query ILIKE '%%환불%%' AND (q.raw_query ILIKE '%%기행%%' OR q.raw_query ILIKE '%%공월%%' OR q.raw_query ILIKE '%%결제%%') THEN 'refund_after_purchase'
                ELSE NULL
            END AS intent_family
        FROM qa_ticket q
    ),
    policy_docs AS (
        SELECT
            d.documents_id,
            d.source_type,
            d.category,
            d.title,
            c.chunk_id,
            c.chunk_order,
            CASE
                WHEN d.documents_id = 'QNA-GSN-5' THEN 'payment_delivery_issue'
                WHEN d.documents_id = 'QNA-GSN-9' THEN 'duplicate_payment'
                WHEN d.documents_id IN ('QNA-GSN-7', 'QNA-GSN-8') THEN 'refund_after_purchase'
                ELSE NULL
            END AS intent_family
        FROM documents d
        JOIN documents_chunks c ON c.document_id = d.documents_id
    ),
    account_ctx AS (
        SELECT
            a.account_id,
            a.account_status,
            a.server_region
        FROM game_accounts a
    ),
    recent_payments AS (
        SELECT
            p.*,
            ROW_NUMBER() OVER (
                PARTITION BY p.account_id
                ORDER BY p.paid_at DESC NULLS LAST, p.payment_id DESC
            ) AS payment_rank
        FROM payments p
    ),
    recent_deliveries AS (
        SELECT
            d.*,
            ROW_NUMBER() OVER (
                PARTITION BY d.account_id
                ORDER BY d.expected_at DESC NULLS LAST, d.delivery_id DESC
            ) AS delivery_rank
        FROM item_delivery_logs d
    ),
    recent_refunds AS (
        SELECT
            p.account_id,
            r.refund_id,
            r.payment_id,
            r.refund_status,
            r.refund_reason,
            r.requested_at,
            r.processed_at,
            ROW_NUMBER() OVER (
                PARTITION BY p.account_id
                ORDER BY r.requested_at DESC NULLS LAST, r.refund_id DESC
            ) AS refund_rank
        FROM payments p
        JOIN refunds r ON r.payment_id = p.payment_id
    )
    SELECT
        t.ticket_id,
        t.account_id,
        t.user_id,
        t.raw_query,
        t.inquiry_created_at,
        t.intent_family,
        a.account_status,
        a.server_region,
        p.payment_id,
        p.product_name,
        p.product_type,
        p.amount,
        p.currency,
        p.payment_method,
        p.payment_status,
        p.paid_at,
        d.delivery_id,
        d.payment_id AS delivery_payment_id,
        d.item_name,
        d.quantity,
        d.delivery_status,
        d.expected_at,
        d.delivered_at,
        r.refund_id,
        r.payment_id AS refund_payment_id,
        r.refund_status,
        r.refund_reason,
        r.requested_at,
        r.processed_at,
        doc.documents_id,
        doc.chunk_id,
        doc.source_type,
        doc.category,
        doc.title,
        doc.chunk_order
    FROM classified_tickets t
    JOIN account_ctx a ON a.account_id = t.account_id
    LEFT JOIN recent_payments p ON p.account_id = t.account_id AND p.payment_rank <= 2
    LEFT JOIN recent_deliveries d ON d.account_id = t.account_id AND d.delivery_rank <= 4
    LEFT JOIN recent_refunds r ON r.account_id = t.account_id AND r.refund_rank <= 2
    JOIN policy_docs doc ON doc.intent_family = t.intent_family
    WHERE t.intent_family IS NOT NULL
    ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC, doc.documents_id, doc.chunk_order
    LIMIT %s
    """
    grouped: dict[int, dict[str, Any]] = {}
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (limit * 8,))
            for row in cur.fetchall():
                ticket_id = int(row["ticket_id"])
                existing = grouped.get(ticket_id)
                if existing is None:
                    existing = {
                        "ticket_id": ticket_id,
                        "routing_target": "DB&DOC",
                        "intent_family": row["intent_family"],
                        "ticket": {
                            "account_id": row["account_id"],
                            "user_id": row["user_id"],
                            "created_at": str(row["inquiry_created_at"]),
                            "question": row["raw_query"],
                        },
                        "gold_facts": {
                            "account": {
                                "account_status": row["account_status"],
                                "server_region": row["server_region"],
                            },
                            "payments": [],
                            "deliveries": [],
                            "refunds": [],
                        },
                        "gold_policy": {"documents": []},
                    }
                    grouped[ticket_id] = existing
                payment = {
                    "payment_id": row["payment_id"],
                    "product_name": row["product_name"],
                    "product_type": row["product_type"],
                    "amount": row["amount"],
                    "currency": row["currency"],
                    "payment_method": row["payment_method"],
                    "payment_status": row["payment_status"],
                    "paid_at": str(row["paid_at"]) if row["paid_at"] else None,
                }
                if row["payment_id"] is not None and payment not in existing["gold_facts"]["payments"]:
                    existing["gold_facts"]["payments"].append(payment)
                delivery = {
                    "delivery_id": row["delivery_id"],
                    "payment_id": row["delivery_payment_id"],
                    "item_name": row["item_name"],
                    "quantity": row["quantity"],
                    "delivery_status": row["delivery_status"],
                    "expected_at": str(row["expected_at"]) if row["expected_at"] else None,
                    "delivered_at": str(row["delivered_at"]) if row["delivered_at"] else None,
                }
                if row["delivery_id"] is not None and delivery not in existing["gold_facts"]["deliveries"]:
                    existing["gold_facts"]["deliveries"].append(delivery)
                refund = {
                    "refund_id": row["refund_id"],
                    "payment_id": row["refund_payment_id"],
                    "refund_status": row["refund_status"],
                    "refund_reason": row["refund_reason"],
                    "requested_at": str(row["requested_at"]) if row["requested_at"] else None,
                    "processed_at": str(row["processed_at"]) if row["processed_at"] else None,
                }
                if row["refund_id"] is not None and refund not in existing["gold_facts"]["refunds"]:
                    existing["gold_facts"]["refunds"].append(refund)
                document = {
                    "document_id": row["documents_id"],
                    "chunk_id": row["chunk_id"],
                    "source_type": row["source_type"],
                    "category": row["category"],
                    "title": row["title"],
                }
                if document not in existing["gold_policy"]["documents"]:
                    existing["gold_policy"]["documents"].append(document)
    results = []
    for item in grouped.values():
        intent_family = str(item.pop("intent_family"))
        item["gold_policy"]["must_include"] = _must_include_for_hybrid(intent_family)
        item["must_not_include"] = _must_not_include_for_hybrid(intent_family)
        results.append(item)
    return results[:limit]


def main() -> None:
    doc_only = fetch_doc_only_candidates()
    db_only = fetch_db_only_candidates()
    hybrid = fetch_hybrid_candidates()
    payload = {
        "dataset_info": {
            "name": "cs_auto_routing_target_gold_dataset_live_candidates",
            "created_at": "2026-06-18",
            "source": "live_db",
            "database": "game_cs",
            "schema": "public",
            "counts": {
                "doc_only": len(doc_only),
                "DB_only": len(db_only),
                "DB&DOC": len(hybrid),
                "total": len(doc_only) + len(db_only) + len(hybrid),
            },
            "notes": [
                "This file is an auto-expanded candidate dataset from live DB rows.",
                "Use this as a review queue or semi-automatic eval dataset.",
                "Each example uses live structured evidence and live document IDs/chunk IDs.",
            ],
        },
        "examples": doc_only + db_only + hybrid,
    }
    OUTPUT_PATH.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(OUTPUT_PATH))


if __name__ == "__main__":
    main()
