from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "apps" / "cs_auto" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from common.db.connection import db_connection
from apps.cs_auto.backend.agents.tool.dbsearch import DEFAULT_QUERY_TYPE_BY_CATEGORY
from apps.cs_auto.backend.agents.tool.docsearch import DocumentRetriever

OUTPUT_PATH = Path(__file__).with_name("answer_agent_eval_dataset_live.json")
SUPPORTED_ROUTING_TARGETS = ("doc_only", "DB_only", "DB&DOC", "fixed_answer")
DEFAULT_TOTAL_SAMPLES = 64
MIN_SAMPLE_COUNTS = {
    "doc_only": 0,
    "DB_only": 10,
    "DB&DOC": 10,
    "fixed_answer": 10,
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def fetch_routing_distribution() -> dict[str, int]:
    sql = """
    WITH latest_analysis AS (
        SELECT DISTINCT ON (a.ticket_id)
            COALESCE(a.routing_target, 'fixed_answer') AS routing_target
        FROM ticket_analysis a
        ORDER BY a.ticket_id, a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    )
    SELECT
        routing_target,
        COUNT(*) AS ticket_count
    FROM latest_analysis
    WHERE routing_target = ANY(%s)
    GROUP BY routing_target
    """
    distribution = {routing_target: 0 for routing_target in SUPPORTED_ROUTING_TARGETS}
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (list(SUPPORTED_ROUTING_TARGETS),))
            for row in cur.fetchall():
                distribution[str(row["routing_target"])] = int(row["ticket_count"])
    return distribution


def allocate_sample_counts(
    distribution: dict[str, int],
    total_samples: int = DEFAULT_TOTAL_SAMPLES,
) -> dict[str, int]:
    positive_targets = [target for target, count in distribution.items() if count > 0]
    if not positive_targets:
        raise ValueError("No routing_target rows found in live DB")

    min_required = sum(min(MIN_SAMPLE_COUNTS.get(target, 0), distribution.get(target, 0)) for target in positive_targets)
    target_total = max(total_samples, len(positive_targets), min_required)
    raw_total = sum(distribution[target] for target in positive_targets)

    allocations = {target: 0 for target in SUPPORTED_ROUTING_TARGETS}
    fractions: list[tuple[float, str]] = []
    used = 0

    for target in positive_targets:
        minimum = min(MIN_SAMPLE_COUNTS.get(target, 0), distribution.get(target, 0))
        allocations[target] = minimum
        used += minimum

    remaining_total = max(target_total - used, 0)
    if remaining_total == 0:
        return allocations

    for target in positive_targets:
        remaining_capacity = max(distribution[target] - allocations[target], 0)
        if remaining_capacity <= 0:
            fractions.append((0.0, target))
            continue
        exact = (distribution[target] / raw_total) * remaining_total
        base = min(remaining_capacity, math.floor(exact))
        allocations[target] += base
        used += base
        fractions.append((exact - math.floor(exact), target))

    if used > target_total:
        removable = sorted(
            (
                (fractional_part, target)
                for fractional_part, target in fractions
                if allocations[target] > min(MIN_SAMPLE_COUNTS.get(target, 0), distribution.get(target, 0))
            ),
            key=lambda item: item[0],
        )
        idx = 0
        while used > target_total and idx < len(removable):
            _, target = removable[idx]
            allocations[target] -= 1
            used -= 1
            if allocations[target] > min(MIN_SAMPLE_COUNTS.get(target, 0), distribution.get(target, 0)):
                idx += 1
            else:
                removable = [item for item in removable if item[1] != target]
        while used > target_total:
            for target in positive_targets:
                if used <= target_total:
                    break
                if allocations[target] > min(MIN_SAMPLE_COUNTS.get(target, 0), distribution.get(target, 0)):
                    allocations[target] -= 1
                    used -= 1

    if used < target_total:
        for _, target in sorted(fractions, reverse=True):
            if used >= target_total:
                break
            if allocations[target] >= distribution[target]:
                continue
            allocations[target] += 1
            used += 1
        idx = 0
        exhausted_rounds = 0
        while used < target_total and exhausted_rounds < len(positive_targets):
            target = positive_targets[idx % len(positive_targets)]
            if allocations[target] < distribution[target]:
                allocations[target] += 1
                used += 1
                exhausted_rounds = 0
            else:
                exhausted_rounds += 1
            idx += 1

    return allocations


def fetch_fixed_answer_candidates(limit: int) -> list[dict[str, Any]]:
    sql = """
    WITH latest_analysis AS (
        SELECT DISTINCT ON (q.ticket_id)
            q.ticket_id,
            q.account_id,
            q.user_id,
            COALESCE(q.title, '') AS title,
            COALESCE(q.raw_query, '') AS raw_query,
            COALESCE(q.source_type, '') AS source_type,
            COALESCE(q.status, '') AS status,
            q.inquiry_created_at,
            q.assignee_admin_id,
            a.analysis_id,
            COALESCE(a.category, 'general') AS category,
            COALESCE(a.enriched_query, '') AS enriched_query,
            COALESCE(a.risk_level, '') AS risk_level,
            COALESCE(a.sentiment, '') AS sentiment,
            COALESCE(a.routing_target, 'fixed_answer') AS routing_target,
            COALESCE(a.summary, '') AS summary,
            a.analyzed_at
        FROM qa_ticket q
        JOIN ticket_analysis a ON a.ticket_id = q.ticket_id
        WHERE COALESCE(a.routing_target, 'fixed_answer') = 'fixed_answer'
        ORDER BY q.ticket_id, a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    )
    SELECT *
    FROM latest_analysis
    ORDER BY analyzed_at DESC NULLS LAST, inquiry_created_at DESC NULLS LAST, ticket_id DESC
    LIMIT %s
    """
    results: list[dict[str, Any]] = []
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (limit,))
            for row in cur.fetchall():
                summary = str(row["summary"] or "").strip()
                results.append(
                    {
                        "ticket_id": int(row["ticket_id"]),
                        "routing_target": "fixed_answer",
                        "ticket": {
                            "account_id": row["account_id"],
                            "user_id": row["user_id"],
                            "created_at": str(row["inquiry_created_at"]) if row["inquiry_created_at"] else None,
                            "question": row["raw_query"],
                        },
                        "answer_target": {
                            "ticket_id": row["ticket_id"],
                            "account_id": row["account_id"],
                            "user_id": row["user_id"],
                            "title": row["title"],
                            "raw_query": row["raw_query"],
                            "source_type": row["source_type"],
                            "status": row["status"],
                            "inquiry_created_at": row["inquiry_created_at"],
                            "assignee_admin_id": row["assignee_admin_id"],
                            "analysis_id": row["analysis_id"],
                            "category": row["category"],
                            "enriched_query": row["enriched_query"],
                            "risk_level": row["risk_level"],
                            "sentiment": row["sentiment"],
                            "routing_target": row["routing_target"],
                            "summary": row["summary"],
                            "analyzed_at": row["analyzed_at"],
                        },
                        "gold_fixed_answer": {
                            "summary_excerpt": summary[:300],
                            "expected_evidence": {
                                "source_type": "fixed_answer",
                                "source_id": row["analysis_id"],
                            },
                        },
                        "must_include": [
                            "분석 요약(summary)에 있는 사실만 사용",
                            "추가 정책/주문/결제 상태를 새로 만들지 않음",
                        ],
                        "must_not_include": [
                            "DB 검색이나 문서 검색을 한 것처럼 단정",
                            "summary에 없는 조치, 보상, 처리 완료 상태를 생성",
                        ],
                    }
                )
    return results


def fetch_doc_only_candidates(limit: int) -> list[dict[str, Any]]:
    sql = """
    WITH latest_analysis AS (
        SELECT DISTINCT ON (a.ticket_id)
            a.ticket_id,
            COALESCE(a.routing_target, 'fixed_answer') AS routing_target
        FROM ticket_analysis a
        ORDER BY a.ticket_id, a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    ),
    classified_tickets AS (
        SELECT
            q.ticket_id,
            q.account_id,
            q.user_id,
            q.raw_query,
            q.inquiry_created_at,
            CASE
                WHEN q.raw_query ILIKE '%%비밀번호%%' OR q.title ILIKE '%%비밀번호%%' THEN 'account_password'
                WHEN q.raw_query ILIKE '%%최근%%공지%%' OR q.raw_query ILIKE '%%업데이트%%공지%%' OR q.raw_query ILIKE '%%최신 공지%%' THEN 'latest_notice'
                WHEN q.raw_query ILIKE '%%우편%%' OR q.raw_query ILIKE '%%보상%%' THEN 'mail_reward'
                ELSE NULL
            END AS intent_family
        FROM qa_ticket q
        JOIN latest_analysis la ON la.ticket_id = q.ticket_id
        WHERE la.routing_target = 'doc_only'
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
            cur.execute(sql, (limit * 4,))
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
                            "created_at": str(row["inquiry_created_at"]) if row["inquiry_created_at"] else None,
                            "question": row["raw_query"],
                        },
                        "gold_policy": {"documents": []},
                        "must_include": [
                            "문서에 있는 정책/공지/절차만 안내",
                            "DB 상태를 확인한 것처럼 말하지 않음",
                        ],
                        "must_not_include": [
                            "주문/결제/환불 상태를 임의로 생성",
                            "문서에 없는 보상 또는 예외 처리를 확정",
                        ],
                    }
                    grouped[ticket_id] = existing
                if len(existing["gold_policy"]["documents"]) < 3:
                    existing["gold_policy"]["documents"].append(
                        {
                            "document_id": row["documents_id"],
                            "chunk_id": row["chunk_id"],
                            "source_type": row["source_type"],
                            "category": row["category"],
                            "title": row["title"],
                        }
                    )
    return list(grouped.values())[:limit]


def fetch_db_only_candidates(limit: int) -> list[dict[str, Any]]:
    sql = """
    WITH latest_analysis AS (
        SELECT DISTINCT ON (a.ticket_id)
            a.ticket_id,
            COALESCE(a.routing_target, 'fixed_answer') AS routing_target
        FROM ticket_analysis a
        ORDER BY a.ticket_id, a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    ),
    classified_tickets AS (
        SELECT
            q.ticket_id,
            q.account_id,
            q.user_id,
            q.raw_query,
            q.inquiry_created_at
        FROM qa_ticket q
        JOIN latest_analysis la ON la.ticket_id = q.ticket_id
        WHERE la.routing_target = 'DB_only'
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
    )
    SELECT
        t.ticket_id,
        t.account_id,
        t.user_id,
        t.raw_query,
        t.inquiry_created_at,
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
        ld.delivered_at
    FROM classified_tickets t
    JOIN game_accounts a ON a.account_id = t.account_id
    LEFT JOIN latest_payment lp ON lp.account_id = t.account_id
    LEFT JOIN latest_refund lr ON lr.account_id = t.account_id
    LEFT JOIN latest_delivery ld ON ld.account_id = t.account_id
    ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
    LIMIT %s
    """
    results: list[dict[str, Any]] = []
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (limit,))
            for row in cur.fetchall():
                results.append(
                    {
                        "ticket_id": int(row["ticket_id"]),
                        "routing_target": "DB_only",
                        "ticket": {
                            "account_id": row["account_id"],
                            "user_id": row["user_id"],
                            "created_at": str(row["inquiry_created_at"]) if row["inquiry_created_at"] else None,
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
                        },
                        "must_include": [
                            "live DB에 있는 최신 상태만 설명",
                            "문서 정책을 근거 없이 끌어오지 않음",
                        ],
                        "must_not_include": [
                            "DB에 없는 결제/환불/지급 상태를 생성",
                            "약관이나 공지 내용을 확인한 것처럼 단정",
                        ],
                    }
                )
    return results


def fetch_hybrid_candidates(limit: int) -> list[dict[str, Any]]:
    sql = """
    WITH latest_analysis AS (
        SELECT DISTINCT ON (a.ticket_id)
            a.ticket_id,
            COALESCE(a.routing_target, 'fixed_answer') AS routing_target
        FROM ticket_analysis a
        ORDER BY a.ticket_id, a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    ),
    classified_tickets AS (
        SELECT
            q.ticket_id,
            q.account_id,
            q.user_id,
            q.raw_query,
            q.inquiry_created_at,
            CASE
                WHEN q.raw_query ILIKE '%%로드%%' OR q.raw_query ILIKE '%%지급%%' OR q.raw_query ILIKE '%%미지급%%' OR q.raw_query ILIKE '%%상품%%로드%%' THEN 'payment_delivery_issue'
                WHEN q.raw_query ILIKE '%%중복결제%%' OR q.raw_query ILIKE '%%중복 결제%%' THEN 'duplicate_payment'
                WHEN q.raw_query ILIKE '%%환불%%' AND (q.raw_query ILIKE '%%결제%%' OR q.raw_query ILIKE '%%구매%%') THEN 'refund_after_purchase'
                ELSE NULL
            END AS intent_family
        FROM qa_ticket q
        JOIN latest_analysis la ON la.ticket_id = q.ticket_id
        WHERE la.routing_target = 'DB&DOC'
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
    JOIN game_accounts a ON a.account_id = t.account_id
    LEFT JOIN recent_payments p ON p.account_id = t.account_id AND p.payment_rank <= 2
    LEFT JOIN recent_deliveries d ON d.account_id = t.account_id AND d.delivery_rank <= 3
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
                        "ticket": {
                            "account_id": row["account_id"],
                            "user_id": row["user_id"],
                            "created_at": str(row["inquiry_created_at"]) if row["inquiry_created_at"] else None,
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
                        "must_include": [
                            "DB 상태와 문서 정책을 함께 반영",
                            "사실과 정책의 출처를 섞지 않고 일관되게 답변",
                        ],
                        "must_not_include": [
                            "문서만으로 지급 상태를 확정",
                            "DB 사실만으로 정책 예외를 확정",
                        ],
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
    return list(grouped.values())[:limit]


def fetch_answer_target_map(ticket_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ticket_ids:
        return {}
    sql = """
    WITH latest_analysis AS (
        SELECT DISTINCT ON (a.ticket_id)
            a.ticket_id,
            a.analysis_id,
            COALESCE(a.category, 'general') AS category,
            COALESCE(a.enriched_query, '') AS enriched_query,
            COALESCE(a.risk_level, '') AS risk_level,
            COALESCE(a.sentiment, '') AS sentiment,
            COALESCE(a.routing_target, 'fixed_answer') AS routing_target,
            COALESCE(a.summary, '') AS summary,
            a.analyzed_at
        FROM ticket_analysis a
        WHERE a.ticket_id = ANY(%s)
        ORDER BY a.ticket_id, a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    )
    SELECT
        q.ticket_id,
        q.account_id,
        q.user_id,
        COALESCE(q.title, '') AS title,
        COALESCE(q.raw_query, '') AS raw_query,
        COALESCE(q.source_type, '') AS source_type,
        COALESCE(q.status, '') AS status,
        q.inquiry_created_at,
        q.assignee_admin_id,
        la.analysis_id,
        la.category,
        la.enriched_query,
        la.risk_level,
        la.sentiment,
        la.routing_target,
        la.summary,
        la.analyzed_at
    FROM qa_ticket q
    LEFT JOIN latest_analysis la ON la.ticket_id = q.ticket_id
    WHERE q.ticket_id = ANY(%s)
    """
    target_map: dict[int, dict[str, Any]] = {}
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (ticket_ids, ticket_ids))
            for row in cur.fetchall():
                ticket_id = int(row["ticket_id"])
                target_map[ticket_id] = {
                    "ticket_id": ticket_id,
                    "account_id": row["account_id"],
                    "user_id": row["user_id"],
                    "title": row["title"],
                    "raw_query": row["raw_query"],
                    "source_type": row["source_type"],
                    "status": row["status"],
                    "inquiry_created_at": row["inquiry_created_at"],
                    "assignee_admin_id": row["assignee_admin_id"],
                    "analysis_id": row["analysis_id"],
                    "category": row["category"],
                    "enriched_query": row["enriched_query"],
                    "risk_level": row["risk_level"],
                    "sentiment": row["sentiment"],
                    "routing_target": row["routing_target"] or "fixed_answer",
                    "summary": row["summary"],
                    "analyzed_at": row["analyzed_at"],
                }
    return target_map


def _infer_gold_query_type(answer_target: dict[str, Any]) -> str:
    category = str(answer_target.get("category") or "general").lower()
    default_query_type = DEFAULT_QUERY_TYPE_BY_CATEGORY.get(category)
    if default_query_type is not None:
        return str(default_query_type)
    question = str(answer_target.get("enriched_query") or answer_target.get("raw_query") or "").lower()
    if any(keyword in question for keyword in ("결제", "payment", "refund", "환불", "delivery", "지급")):
        return "text_to_sql"
    return "fixed_sql"


def _build_ticket_payload_from_answer_target(answer_target: dict[str, Any]) -> dict[str, object]:
    return {
        "ticket_id": answer_target.get("ticket_id"),
        "account_id": answer_target.get("account_id"),
        "user_id": answer_target.get("user_id"),
        "title": answer_target.get("title") or "",
        "raw_query": answer_target.get("raw_query") or "",
        "source_type": answer_target.get("source_type") or "",
        "status": answer_target.get("status") or "",
        "inquiry_created_at": answer_target.get("inquiry_created_at"),
        "assignee_admin_id": answer_target.get("assignee_admin_id"),
    }


def _build_analysis_payload_from_answer_target(answer_target: dict[str, Any]) -> dict[str, object]:
    return {
        "analysis_id": answer_target.get("analysis_id"),
        "category": answer_target.get("category") or "general",
        "enriched_query": answer_target.get("enriched_query") or "",
        "risk_level": answer_target.get("risk_level") or "",
        "sentiment": answer_target.get("sentiment") or "",
        "routing_target": answer_target.get("routing_target") or "fixed_answer",
        "summary": answer_target.get("summary") or "",
        "analyzed_at": answer_target.get("analyzed_at"),
        "account_id": answer_target.get("account_id"),
        "user_id": answer_target.get("user_id"),
    }


def _document_to_gold_entry(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": document.get("document_id"),
        "chunk_id": document.get("chunk_id"),
        "source_type": document.get("source_type"),
        "category": document.get("category"),
        "title": document.get("title"),
    }


def enrich_examples_with_gold_signals(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    doc_retriever = DocumentRetriever()
    enriched_examples: list[dict[str, Any]] = []

    for example in examples:
        enriched = dict(example)
        answer_target = dict(enriched.get("answer_target") or {})
        routing_target = str(enriched.get("routing_target") or answer_target.get("routing_target") or "fixed_answer")

        if routing_target in {"DB_only", "DB&DOC"} and not str(enriched.get("gold_query_type") or "").strip():
            enriched["gold_query_type"] = _infer_gold_query_type(answer_target)

        if routing_target in {"doc_only", "DB&DOC"}:
            gold_policy = dict(enriched.get("gold_policy") or {})
            gold_documents = gold_policy.get("documents") or []
            if not gold_documents:
                try:
                    ticket_payload = _build_ticket_payload_from_answer_target(answer_target)
                    analysis_payload = _build_analysis_payload_from_answer_target(answer_target)
                    query = doc_retriever.query_builder.build(ticket_payload, analysis_payload)
                    documents = doc_retriever.document_searcher.search(query)
                    gold_policy["documents"] = [_document_to_gold_entry(document.model_dump()) for document in documents[:3]]
                    enriched["gold_policy"] = gold_policy
                except Exception:
                    gold_policy.setdefault("documents", [])
                    enriched["gold_policy"] = gold_policy

        enriched_examples.append(enriched)

    return enriched_examples


def fetch_generic_route_candidates(routing_target: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    sql = """
    WITH latest_analysis AS (
        SELECT DISTINCT ON (a.ticket_id)
            a.ticket_id,
            a.analysis_id,
            COALESCE(a.category, 'general') AS category,
            COALESCE(a.enriched_query, '') AS enriched_query,
            COALESCE(a.risk_level, '') AS risk_level,
            COALESCE(a.sentiment, '') AS sentiment,
            COALESCE(a.routing_target, 'fixed_answer') AS routing_target,
            COALESCE(a.summary, '') AS summary,
            a.analyzed_at
        FROM ticket_analysis a
        WHERE COALESCE(a.routing_target, 'fixed_answer') = %s
        ORDER BY a.ticket_id, a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
    )
    SELECT
        q.ticket_id,
        q.account_id,
        q.user_id,
        COALESCE(q.title, '') AS title,
        COALESCE(q.raw_query, '') AS raw_query,
        COALESCE(q.source_type, '') AS source_type,
        COALESCE(q.status, '') AS status,
        q.inquiry_created_at,
        q.assignee_admin_id,
        la.analysis_id,
        la.category,
        la.enriched_query,
        la.risk_level,
        la.sentiment,
        la.routing_target,
        la.summary,
        la.analyzed_at
    FROM qa_ticket q
    JOIN latest_analysis la ON la.ticket_id = q.ticket_id
    ORDER BY la.analyzed_at DESC NULLS LAST, q.inquiry_created_at DESC NULLS LAST, q.ticket_id DESC
    LIMIT %s
    """
    examples: list[dict[str, Any]] = []
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (routing_target, limit))
            for row in cur.fetchall():
                summary = str(row["summary"] or "").strip()
                example = {
                    "ticket_id": int(row["ticket_id"]),
                    "routing_target": routing_target,
                    "ticket": {
                        "account_id": row["account_id"],
                        "user_id": row["user_id"],
                        "created_at": str(row["inquiry_created_at"]) if row["inquiry_created_at"] else None,
                        "question": row["raw_query"],
                    },
                    "answer_target": {
                        "ticket_id": row["ticket_id"],
                        "account_id": row["account_id"],
                        "user_id": row["user_id"],
                        "title": row["title"],
                        "raw_query": row["raw_query"],
                        "source_type": row["source_type"],
                        "status": row["status"],
                        "inquiry_created_at": row["inquiry_created_at"],
                        "assignee_admin_id": row["assignee_admin_id"],
                        "analysis_id": row["analysis_id"],
                        "category": row["category"],
                        "enriched_query": row["enriched_query"],
                        "risk_level": row["risk_level"],
                        "sentiment": row["sentiment"],
                        "routing_target": row["routing_target"],
                        "summary": row["summary"],
                        "analyzed_at": row["analyzed_at"],
                    },
                    "eval_focus": _eval_focus_for_target(routing_target),
                    "summary_oracle": {
                        "summary_excerpt": summary[:300],
                    },
                }
                if routing_target == "doc_only":
                    example["gold_policy"] = {"documents": []}
                    example["must_include"] = [
                        "문서/정책 기반 안내로 답변",
                        "summary 범위를 넘는 DB 상태 단정 금지",
                    ]
                    example["must_not_include"] = [
                        "결제/환불/지급 상태를 사실처럼 생성",
                        "summary에 없는 예외 처리나 보상을 확정",
                    ]
                elif routing_target == "DB&DOC":
                    example["gold_policy"] = {"documents": []}
                    example["gold_facts"] = {}
                    example["must_include"] = [
                        "DB 상태와 정책 안내가 둘 다 필요한 문의로 평가",
                        "summary와 실제 route에 맞는 혼합 답변 구성",
                    ]
                    example["must_not_include"] = [
                        "문서만으로 상태를 단정",
                        "DB 사실만으로 정책 예외를 확정",
                    ]
                elif routing_target == "DB_only":
                    example["gold_facts"] = {}
                    example["must_include"] = [
                        "DB 조회 결과 위주로 답변",
                        "summary 범위를 넘는 정책 단정 금지",
                    ]
                    example["must_not_include"] = [
                        "문서 정책을 확인한 것처럼 단정",
                    ]
                else:
                    example["gold_fixed_answer"] = {
                        "summary_excerpt": summary[:300],
                        "expected_evidence": {
                            "source_type": "fixed_answer",
                            "source_id": row["analysis_id"],
                        },
                    }
                    example["must_include"] = [
                        "summary에 있는 사실만 사용",
                    ]
                    example["must_not_include"] = [
                        "추가 상태를 생성",
                    ]
                examples.append(example)
    return examples


def attach_answer_targets(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_map = fetch_answer_target_map([int(example["ticket_id"]) for example in examples])
    enriched_examples: list[dict[str, Any]] = []
    for example in examples:
        ticket_id = int(example["ticket_id"])
        answer_target = target_map.get(ticket_id)
        if answer_target is None:
            continue
        enriched = dict(example)
        enriched["answer_target"] = answer_target
        enriched["eval_focus"] = _eval_focus_for_target(str(enriched.get("routing_target") or "fixed_answer"))
        enriched_examples.append(enriched)
    return enriched_examples


def _eval_focus_for_target(routing_target: str) -> list[str]:
    if routing_target == "DB_only":
        return ["db_retrieval", "factual_grounding", "no_policy_hallucination"]
    if routing_target == "doc_only":
        return ["document_retrieval", "policy_grounding", "no_db_claims"]
    if routing_target == "DB&DOC":
        return ["hybrid_retrieval", "conflict_resolution", "policy_plus_state"]
    return ["fixed_answer_fallback", "summary_grounding", "no_extra_claims"]


def _filter_examples_by_live_routing(
    examples: list[dict[str, Any]],
    expected_routing_target: str,
    limit: int,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for example in attach_answer_targets(examples):
        actual_target = str(example["answer_target"].get("routing_target") or "fixed_answer")
        if actual_target != expected_routing_target:
            continue
        example["routing_target"] = expected_routing_target
        example["eval_focus"] = _eval_focus_for_target(expected_routing_target)
        matched.append(example)
        if len(matched) >= limit:
            break
    return matched


def _dedupe_examples(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_ticket_ids: set[int] = set()
    for example in examples:
        ticket_id = int(example["ticket_id"])
        if ticket_id in seen_ticket_ids:
            continue
        seen_ticket_ids.add(ticket_id)
        deduped.append(example)
    return deduped


def build_examples(sample_counts: dict[str, int]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []

    doc_only = _filter_examples_by_live_routing(
        fetch_doc_only_candidates(limit=max(sample_counts["doc_only"] * 10, sample_counts["doc_only"])),
        expected_routing_target="doc_only",
        limit=sample_counts["doc_only"],
    )
    if len(doc_only) < sample_counts["doc_only"]:
        seen_ids = {int(example["ticket_id"]) for example in doc_only}
        for example in fetch_generic_route_candidates("doc_only", sample_counts["doc_only"] * 3):
            if int(example["ticket_id"]) in seen_ids:
                continue
            doc_only.append(example)
            seen_ids.add(int(example["ticket_id"]))
            if len(doc_only) >= sample_counts["doc_only"]:
                break
    examples.extend(doc_only[: sample_counts["doc_only"]])

    db_only = _filter_examples_by_live_routing(
        fetch_db_only_candidates(limit=max(sample_counts["DB_only"] * 10, sample_counts["DB_only"])),
        expected_routing_target="DB_only",
        limit=sample_counts["DB_only"],
    )
    if len(db_only) < sample_counts["DB_only"]:
        seen_ids = {int(example["ticket_id"]) for example in db_only}
        for example in fetch_generic_route_candidates("DB_only", sample_counts["DB_only"] * 3):
            if int(example["ticket_id"]) in seen_ids:
                continue
            db_only.append(example)
            seen_ids.add(int(example["ticket_id"]))
            if len(db_only) >= sample_counts["DB_only"]:
                break
    examples.extend(db_only[: sample_counts["DB_only"]])

    hybrid = _filter_examples_by_live_routing(
        fetch_hybrid_candidates(limit=max(sample_counts["DB&DOC"] * 10, sample_counts["DB&DOC"])),
        expected_routing_target="DB&DOC",
        limit=sample_counts["DB&DOC"],
    )
    if len(hybrid) < sample_counts["DB&DOC"]:
        seen_ids = {int(example["ticket_id"]) for example in hybrid}
        for example in fetch_generic_route_candidates("DB&DOC", sample_counts["DB&DOC"] * 3):
            if int(example["ticket_id"]) in seen_ids:
                continue
            hybrid.append(example)
            seen_ids.add(int(example["ticket_id"]))
            if len(hybrid) >= sample_counts["DB&DOC"]:
                break
    examples.extend(hybrid[: sample_counts["DB&DOC"]])

    fixed_answer = fetch_fixed_answer_candidates(limit=sample_counts["fixed_answer"])
    if len(fixed_answer) < sample_counts["fixed_answer"]:
        seen_ids = {int(example["ticket_id"]) for example in fixed_answer}
        for example in fetch_generic_route_candidates("fixed_answer", sample_counts["fixed_answer"] * 3):
            if int(example["ticket_id"]) in seen_ids:
                continue
            fixed_answer.append(example)
            seen_ids.add(int(example["ticket_id"]))
            if len(fixed_answer) >= sample_counts["fixed_answer"]:
                break
    examples.extend(fixed_answer[: sample_counts["fixed_answer"]])
    return enrich_examples_with_gold_signals(_dedupe_examples(examples))


def main() -> None:
    live_distribution = fetch_routing_distribution()
    sample_counts = allocate_sample_counts(live_distribution)
    examples = build_examples(sample_counts)
    actual_counts = Counter(str(example["routing_target"]) for example in examples)

    payload = {
        "dataset_info": {
            "name": "cs_auto_answer_agent_eval_dataset_live",
            "created_at": datetime.now(UTC).isoformat(),
            "source": "live_db",
            "database": "game_cs",
            "schema": "public",
            "reference_dataset": "routing_target_gold_dataset_live_candidates.json",
            "target_module": "apps/cs_auto/backend/agents/answer_agent.py",
            "counts": {
                **{target: actual_counts.get(target, 0) for target in SUPPORTED_ROUTING_TARGETS},
                "total": len(examples),
            },
            "live_routing_distribution": live_distribution,
            "requested_sample_counts": sample_counts,
            "notes": [
                "This dataset follows the routing_target candidate dataset structure as the single reference.",
                "Each example includes the full answer_target payload required by answer_agent.AnswerTarget.",
                "Sample allocation follows the live ticket_analysis routing_target distribution.",
                "fixed_answer examples are included to evaluate fallback-only behavior.",
            ],
        },
        "examples": _json_safe(examples),
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(OUTPUT_PATH))


if __name__ == "__main__":
    main()
