"""FastAPI endpoints for dashboard summaries and ticket detail."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from psycopg.rows import dict_row

from src.common.db.connection import db_connection
from src.dashboard.workflow.graph import run_dashboard_workflow


app = FastAPI(title="Dashboard API", version="1.0.0")


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _latest_analysis_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                a.analysis_id,
                a.category,
                a.risk_level,
                a.sentiment,
                a.routing_target,
                a.analyzed_at
            FROM ticket_analysis a
            WHERE a.ticket_id = t.ticket_id
            ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
            LIMIT 1
        ) latest_analysis ON TRUE
    """


def _latest_draft_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT d.draft_id, d.created_at
            FROM answer_draft d
            WHERE d.ticket_id = t.ticket_id
            ORDER BY d.created_at DESC NULLS LAST, d.draft_id DESC
            LIMIT 1
        ) latest_draft ON TRUE
    """


def _latest_response_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT fr.response_id, fr.created_at, fr.safety_action
            FROM final_response fr
            WHERE fr.ticket_id = t.ticket_id
            ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
            LIMIT 1
        ) latest_response ON TRUE
    """


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/summary/overview")
def summary_overview(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    return jsonable_encoder(run_dashboard_workflow("overview", days))


@app.get("/summary/risk")
def summary_risk(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    return jsonable_encoder(run_dashboard_workflow("risk", days))


@app.get("/summary/quality")
def summary_quality(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    return jsonable_encoder(run_dashboard_workflow("quality", days))


@app.get("/summary/all")
def summary_all(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    return jsonable_encoder(run_dashboard_workflow("all", days))


@app.get("/tickets")
def list_tickets(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    where_sql = "WHERE 1 = 1"
    params: list[Any] = []
    if status:
        where_sql += " AND t.status = %s"
        params.append(status)
    params.append(limit)

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = _fetch_all(
                cur,
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.status,
                    t.source_type,
                    t.inquiry_created_at,
                    u.nickname,
                    latest_analysis.category,
                    latest_analysis.risk_level,
                    latest_analysis.routing_target,
                    latest_draft.draft_id,
                    latest_response.response_id,
                    latest_response.created_at AS response_created_at
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                {_latest_analysis_join_sql()}
                {_latest_draft_join_sql()}
                {_latest_response_join_sql()}
                {where_sql}
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT %s
                """,
                tuple(params),
            )
    return jsonable_encoder(rows)


@app.get("/tickets/{ticket_id}")
def get_ticket_detail(ticket_id: int) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            ticket = _fetch_one(
                cur,
                """
                SELECT
                    t.*,
                    u.email,
                    u.nickname,
                    u.user_status,
                    u.last_login_at,
                    a.game_name,
                    a.uid,
                    a.server_region,
                    a.progression_level,
                    a.account_status
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN game_accounts a ON a.account_id = t.account_id
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            if ticket is None:
                raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")

            analyses = _fetch_all(
                cur,
                """
                SELECT *
                FROM ticket_analysis
                WHERE ticket_id = %s
                ORDER BY analyzed_at DESC NULLS LAST, analysis_id DESC
                """,
                (ticket_id,),
            )
            drafts = _fetch_all(
                cur,
                """
                SELECT *
                FROM answer_draft
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, draft_id DESC
                """,
                (ticket_id,),
            )
            draft_ids = [draft["draft_id"] for draft in drafts]
            evidence_docs: list[dict[str, Any]] = []
            safety_results: list[dict[str, Any]] = []
            if draft_ids:
                evidence_docs = _fetch_all(
                    cur,
                    """
                    SELECT *
                    FROM evidence_docs
                    WHERE draft_id = ANY(%s)
                    ORDER BY draft_id DESC, retrieval_rank ASC
                    """,
                    (draft_ids,),
                )
                safety_results = _fetch_all(
                    cur,
                    """
                    SELECT *
                    FROM safety_results
                    WHERE draft_id = ANY(%s)
                    ORDER BY checked_at DESC NULLS LAST, safety_id DESC
                    """,
                    (draft_ids,),
                )
            final_responses = _fetch_all(
                cur,
                """
                SELECT *
                FROM final_response
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, response_id DESC
                """,
                (ticket_id,),
            )
            notifications = _fetch_all(
                cur,
                """
                SELECT *
                FROM notification_logs
                WHERE ticket_id = %s
                ORDER BY sent_at DESC NULLS LAST, notification_id DESC
                """,
                (ticket_id,),
            )
            voc_feedback = _fetch_all(
                cur,
                """
                SELECT *
                FROM voc_feedback
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, voc_id DESC
                """,
                (ticket_id,),
            )
    return jsonable_encoder(
        {
            "ticket": ticket,
            "analyses": analyses,
            "drafts": drafts,
            "evidence_docs": evidence_docs,
            "safety_results": safety_results,
            "final_responses": final_responses,
            "notifications": notifications,
            "voc_feedback": voc_feedback,
        }
    )
