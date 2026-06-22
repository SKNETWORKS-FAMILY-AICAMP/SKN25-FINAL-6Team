"""Insight row materialization for weekly report."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection
from common.observability.langfuse import observe_if_enabled
from weekly_report_langfuse import link_weekly_report_trace


_WHITESPACE_RE = re.compile(r"\s+")


def _next_integer_id(cur: Any, table_name: str, id_column: str) -> int:
    cur.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS next_id FROM {table_name}")
    row = cur.fetchone()
    return int(row["next_id"])


def _normalize_text(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def _normalize_summary(value: Any) -> str:
    return _normalize_text(value).lower()


def _normalize_risk_level(value: Any) -> str:
    normalized = _normalize_text(value).upper()
    if normalized == "MEDIUM":
        return "MID"
    if normalized in {"LOW", "MID", "HIGH", "CRITICAL"}:
        return normalized
    return "LOW"


def _latest_analysis_source_sql() -> str:
    return """
        WITH latest_analysis AS (
            SELECT DISTINCT ON (a.ticket_id)
                a.analysis_id,
                a.ticket_id,
                q.user_id,
                q.account_id,
                q.inquiry_created_at,
                COALESCE(
                    NULLIF(BTRIM(a.summary), ''),
                    NULLIF(BTRIM(a.enriched_query), ''),
                    NULLIF(BTRIM(q.raw_query), ''),
                    NULLIF(BTRIM(q.title), '')
                ) AS content_summary,
                COALESCE(NULLIF(BTRIM(a.category), ''), 'general') AS category,
                COALESCE(NULLIF(BTRIM(a.sentiment), ''), 'neutral') AS sentiment,
                COALESCE(NULLIF(BTRIM(a.risk_level), ''), 'LOW') AS risk_level
            FROM ticket_analysis a
            JOIN qa_ticket q ON q.ticket_id = a.ticket_id
            ORDER BY a.ticket_id, a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
        )
        SELECT
            analysis_id,
            ticket_id,
            user_id,
            account_id,
            inquiry_created_at,
            content_summary,
            category,
            sentiment,
            risk_level
        FROM latest_analysis
        ORDER BY ticket_id ASC
    """


def fetch_latest_analysis_source_rows() -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_latest_analysis_source_sql())
            return [dict(row) for row in cur.fetchall()]


def build_insight_rows(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_summaries = {
        int(row["ticket_id"]): _normalize_summary(row.get("content_summary"))
        for row in source_rows
    }
    user_category_counts = Counter(
        (row.get("user_id"), _normalize_text(row.get("category")).lower())
        for row in source_rows
        if row.get("user_id") is not None
    )
    account_category_counts = Counter(
        (row.get("account_id"), _normalize_text(row.get("category")).lower())
        for row in source_rows
        if row.get("account_id") is not None
    )
    summary_category_counts = Counter(
        (_normalize_text(row.get("category")).lower(), normalized_summaries[int(row["ticket_id"])])
        for row in source_rows
        if normalized_summaries[int(row["ticket_id"])]
    )

    pattern_scores_by_ticket: dict[int, int] = {}
    max_pattern_by_category: dict[str, int] = {}
    for row in source_rows:
        ticket_id = int(row["ticket_id"])
        category = _normalize_text(row.get("category")).lower()
        user_score = 0
        if row.get("user_id") is not None:
            user_score = user_category_counts[(row.get("user_id"), category)]
        account_score = 0
        if row.get("account_id") is not None:
            account_score = account_category_counts[(row.get("account_id"), category)]
        summary_score = 0
        summary_key = normalized_summaries[ticket_id]
        if summary_key:
            summary_score = summary_category_counts[(category, summary_key)]

        pattern_score = max(user_score, account_score, summary_score, 1)
        pattern_scores_by_ticket[ticket_id] = pattern_score
        max_pattern_by_category[category] = max(max_pattern_by_category.get(category, 1), pattern_score)

    insight_rows: list[dict[str, Any]] = []
    for row in source_rows:
        ticket_id = int(row["ticket_id"])
        category = _normalize_text(row.get("category"))
        normalized_category = category.lower()
        content_summary = _normalize_text(row.get("content_summary"))
        pattern_score = pattern_scores_by_ticket[ticket_id]
        max_pattern_score = max_pattern_by_category.get(normalized_category, 1)

        if pattern_score <= 1:
            pattern_risk_level = "LOW"
        elif pattern_score == max_pattern_score:
            pattern_risk_level = "HIGH"
        else:
            pattern_risk_level = "MID"

        risk_level = _normalize_risk_level(row.get("risk_level"))

        insight_rows.append(
            {
                "user_id": int(row["user_id"]),
                "ticket_id": ticket_id,
                "account_id": row.get("account_id"),
                "content_summary": content_summary,
                "category": category or "general",
                "sentiment": _normalize_text(row.get("sentiment")) or "neutral",
                "risk_level": risk_level,
                "pattern_risk_level": pattern_risk_level,
                "inquiry_created_at": row.get("inquiry_created_at"),
            }
        )
    return insight_rows


@observe_if_enabled(
    name="weekly_report_sync_insight_rows",
    as_type="tool",
    tags=["weekly-report", "feature:data-sync", "target:insight"],
)
def sync_insight_rows() -> int:
    source_rows = fetch_latest_analysis_source_rows()
    if not source_rows:
        link_weekly_report_trace(
            {"source_rows_count": 0, "inserted_rows_count": 0},
            tags=["weekly-report", "feature:data-sync", "target:insight"],
            output_payload={"source_rows_count": 0, "inserted_rows_count": 0},
            source_rows_count=0,
            inserted_rows_count=0,
        )
        return 0

    insight_rows = build_insight_rows(source_rows)
    ticket_ids = [int(row["ticket_id"]) for row in insight_rows]

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("DELETE FROM insight WHERE ticket_id = ANY(%s)", (ticket_ids,))
            next_id = _next_integer_id(cur, "insight", "insight_id")
            cur.executemany(
                """
                INSERT INTO insight (
                    insight_id,
                    user_id,
                    ticket_id,
                    account_id,
                    content_summary,
                    category,
                    sentiment,
                    risk_level,
                    pattern_risk_level,
                    inquiry_created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        next_id + index,
                        row["user_id"],
                        row["ticket_id"],
                        row["account_id"],
                        row["content_summary"],
                        row["category"],
                        row["sentiment"],
                        row["risk_level"],
                        row["pattern_risk_level"],
                        row["inquiry_created_at"],
                    )
                    for index, row in enumerate(insight_rows)
                ],
            )

    link_weekly_report_trace(
        {"source_rows_count": len(source_rows), "inserted_rows_count": len(insight_rows)},
        tags=["weekly-report", "feature:data-sync", "target:insight"],
        input_payload={"source_rows_count": len(source_rows)},
        output_payload={"inserted_rows_count": len(insight_rows)},
        source_rows_count=len(source_rows),
        inserted_rows_count=len(insight_rows),
    )
    return len(insight_rows)
