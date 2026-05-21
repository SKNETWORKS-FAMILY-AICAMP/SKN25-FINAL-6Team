"""FastAPI endpoints for operation ticket review and answer approval."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from src.common.db.connection import db_connection


app = FastAPI(title="Operation Review API", version="1.0.0")


ReviewDecision = Literal["approved", "rejected", "edited"]


class DraftEditRequest(BaseModel):
    draft_text: str = Field(min_length=1)
    reviewer_id: str | None = None


class ApproveDraftRequest(BaseModel):
    final_text: str | None = None
    reviewer_id: str | None = None


class RejectDraftRequest(BaseModel):
    reason: str = Field(min_length=1)
    reviewer_id: str | None = None


class ReviewActionResponse(BaseModel):
    ticket_id: int
    draft_id: int
    decision: ReviewDecision
    status: str
    response_id: int | None = None


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    cur.execute(sql, params)
    return _row_to_dict(cur.fetchone())


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _ticket_list_where(
    *,
    status: str | None,
    today_only: bool,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("t.status = %s")
        params.append(status)
    if today_only:
        clauses.append(
            "t.inquiry_created_at >= CURRENT_DATE "
            "AND t.inquiry_created_at < CURRENT_DATE + INTERVAL '1 day'"
        )
    if not clauses:
        return "", params
    return f"WHERE {' AND '.join(clauses)}", params


def _list_ticket_rows(
    cur: Any,
    *,
    status: str | None,
    limit: int,
    today_only: bool = False,
) -> list[dict[str, Any]]:
    where_sql, params = _ticket_list_where(status=status, today_only=today_only)
    params.append(limit)
    return _fetch_all(
        cur,
        f"""
        SELECT
            t.ticket_id,
            t.user_id,
            t.account_id,
            t.title,
            t.source_type,
            t.status,
            t.inquiry_created_at,
            u.nickname,
            latest_draft.draft_id,
            latest_draft.created_at AS draft_created_at,
            latest_analysis.risk_level,
            latest_analysis.routing_target
        FROM qa_ticket t
        LEFT JOIN community_users u ON u.user_id = t.user_id
        LEFT JOIN LATERAL (
            SELECT draft_id, created_at
            FROM answer_draft d
            WHERE d.ticket_id = t.ticket_id
            ORDER BY d.created_at DESC NULLS LAST, d.draft_id DESC
            LIMIT 1
        ) latest_draft ON TRUE
        LEFT JOIN LATERAL (
            SELECT risk_level, routing_target
            FROM ticket_analysis a
            WHERE a.ticket_id = t.ticket_id
            ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
            LIMIT 1
        ) latest_analysis ON TRUE
        {where_sql}
        ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _insert_review_log(
    cur: Any,
    *,
    ticket_id: int,
    draft_id: int,
    decision: ReviewDecision,
    reviewer_id: str | None,
    reason: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO admin_event_logs (
            ticket_id, node_name, event_type, status, metadata, created_at
        )
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (
            ticket_id,
            "operation_review_api",
            "human_review",
            decision,
            Json({
                "draft_id": draft_id,
                "reviewer_id": reviewer_id,
                "reason": reason,
            }),
        ),
    )


def _draft_for_update(cur: Any, draft_id: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT draft_id, ticket_id, analysis_id, draft_text, prompt_version, created_at
        FROM answer_draft
        WHERE draft_id = %s
        FOR UPDATE
        """,
        (draft_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"draft not found: {draft_id}")
    return dict(row)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tickets")
def list_tickets(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    today_only: bool = Query(default=False),
) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _list_ticket_rows(
                cur,
                status=status,
                limit=limit,
                today_only=today_only,
            )


@app.get("/tickets/today")
def list_today_tickets(
    status: str | None = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Return tickets operators should check today.

    The date boundary follows the database server's CURRENT_DATE and uses
    qa_ticket.inquiry_created_at as the received timestamp.
    """
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _list_ticket_rows(
                cur,
                status=status,
                limit=limit,
                today_only=True,
            )


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
            review_logs = _fetch_all(
                cur,
                """
                SELECT *
                FROM admin_event_logs
                WHERE ticket_id = %s AND event_type = 'human_review'
                ORDER BY created_at DESC NULLS LAST, log_id DESC
                """,
                (ticket_id,),
            )
    return {
        "ticket": ticket,
        "analyses": analyses,
        "drafts": drafts,
        "evidence_docs": evidence_docs,
        "safety_results": safety_results,
        "final_responses": final_responses,
        "notifications": notifications,
        "review_logs": review_logs,
    }


@app.patch("/drafts/{draft_id}")
def edit_draft(draft_id: int, request: DraftEditRequest) -> ReviewActionResponse:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _draft_for_update(cur, draft_id)
            cur.execute(
                """
                UPDATE answer_draft
                SET draft_text = %s
                WHERE draft_id = %s
                """,
                (request.draft_text, draft_id),
            )
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="edited",
                reviewer_id=request.reviewer_id,
            )
    return ReviewActionResponse(
        ticket_id=draft["ticket_id"],
        draft_id=draft_id,
        decision="edited",
        status="draft_edited",
    )


@app.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, request: ApproveDraftRequest) -> ReviewActionResponse:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _draft_for_update(cur, draft_id)
            final_text = request.final_text or draft["draft_text"]
            cur.execute(
                """
                INSERT INTO final_response (
                    ticket_id, draft_id, final_text, safety_action, created_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING response_id
                """,
                (draft["ticket_id"], draft_id, final_text, "approved"),
            )
            response_id = cur.fetchone()["response_id"]
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                ("closed", draft["ticket_id"]),
            )
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="approved",
                reviewer_id=request.reviewer_id,
            )
    return ReviewActionResponse(
        ticket_id=draft["ticket_id"],
        draft_id=draft_id,
        decision="approved",
        status="closed",
        response_id=response_id,
    )


@app.post("/drafts/{draft_id}/reject")
def reject_draft(draft_id: int, request: RejectDraftRequest) -> ReviewActionResponse:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _draft_for_update(cur, draft_id)
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                ("pending", draft["ticket_id"]),
            )
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="rejected",
                reviewer_id=request.reviewer_id,
                reason=request.reason,
            )
    return ReviewActionResponse(
        ticket_id=draft["ticket_id"],
        draft_id=draft_id,
        decision="rejected",
        status="pending",
    )
