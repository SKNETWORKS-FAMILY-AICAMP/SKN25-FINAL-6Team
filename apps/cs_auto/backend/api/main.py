"""FastAPI endpoints for the operation workflow and human review actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from common.observability.langsmith import configure_langsmith

configure_langsmith("operation")

from common.db.connection import db_connection
from service.review.operation import approve_existing_draft, edit_existing_draft, regenerate_from_draft, run_workflow_step
from service.admin_account_service import login_admin_with_credentials


app = FastAPI(title="Operation Review API", version="2.0.0")
_FRONTEND_STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "static"


@app.middleware("http")
async def cs_auto_prefix_compat(request: Request, call_next: Any) -> Any:
    path = request.scope.get("path", "")
    if path == "/cs-auto":
        request.scope["path"] = "/"
    elif path.startswith("/cs-auto/api/"):
        request.scope["path"] = path.removeprefix("/cs-auto/api")
    elif path.startswith("/cs-auto/"):
        request.scope["path"] = path.removeprefix("/cs-auto")
    return await call_next(request)


ReviewDecision = Literal["approved", "regenerate", "edited"]


# [추가] 티켓 담당자 할당 요청 모델
class AssignRequest(BaseModel):
    reviewer_id: str = Field(min_length=1)


class DraftEditRequest(BaseModel):
    draft_text: str = Field(min_length=1)
    reviewer_id: str | None = None
    reason: str = Field(default="manual edit", min_length=1)


class ApproveDraftRequest(BaseModel):
    final_text: str | None = None
    reviewer_id: str | None = None
    reason: str = Field(default="approved by reviewer", min_length=1)


class RegenerateDraftRequest(BaseModel):
    reason: str = Field(min_length=1)
    reviewer_id: str | None = None


class ResolveTicketRequest(BaseModel):
    reviewer_id: str | None = None
    reason: str = Field(default="resolved by email", min_length=1)


class StartEditRequest(BaseModel):
    reviewer_id: str = Field(min_length=1)


class AdminLoginRequest(BaseModel):
    login_id: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AdminLoginResponse(BaseModel):
    login_success: bool
    admin_id: int | None = None
    login_id: str = ""
    display_name: str | None = None
    role: str | None = None
    message: str = ""


class RunWorkflowResponse(BaseModel):
    ticket_id: int
    status: str
    final_answer: str | None = None
    draft_id: int | None = None
    analysis_id: int | None = None
    response_id: int | None = None


class ReviewActionResponse(BaseModel):
    ticket_id: int
    draft_id: int
    decision: ReviewDecision
    status: str
    response_id: int | None = None
    next_draft_id: int | None = None
    run_workflow_url: str | None = None


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
    source_type: str | None,
    today_only: bool,
    assignee_id: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        if status == "open":
            clauses.append("(t.source_type = 'naver_cafe' AND t.status = 'open')")
        elif status == "pending":
            clauses.append(
                "((t.source_type = 'chatbot' AND t.status = 'pending') "
                "OR (t.source_type = 'naver_cafe' AND t.status = 'pending') "
                "OR t.status = 'human_review_pending')"
            )
        else:
            clauses.append("t.status = %s")
            params.append(status)
    else:
        clauses.append(
            "((t.source_type = 'chatbot' AND t.status = 'pending') "
            "OR (t.source_type = 'naver_cafe' AND t.status IN ('open', 'pending')) "
            "OR t.status = 'human_review_pending')"
        )
    if source_type:
        clauses.append("t.source_type = %s")
        params.append(source_type)
    if today_only:
        clauses.append(
            "t.inquiry_created_at >= CURRENT_DATE "
            "AND t.inquiry_created_at < CURRENT_DATE + INTERVAL '1 day'"
        )
    # [추가] 담당자 필터 — 할당된 검토 탭에서 사용
    if assignee_id:
        clauses.append("t.assignee_id = %s")
        params.append(assignee_id)
    if not clauses:
        return "", params
    return f"WHERE {' AND '.join(clauses)}", params


# [추가] assignee_id 파라미터 및 SELECT 컬럼 추가
def _list_ticket_rows(
    cur: Any,
    *,
    status: str | None,
    source_type: str | None = None,
    limit: int,
    today_only: bool = False,
    assignee_id: str | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = _ticket_list_where(
        status=status,
        source_type=source_type,
        today_only=today_only,
        assignee_id=assignee_id,
    )
    params.append(limit)
    return _fetch_all(
        cur,
        f"""
        SELECT
            t.ticket_id,
            t.user_id,
            t.account_id,
            t.title,
            t.raw_query,
            t.source_type,
            CASE
                WHEN t.status = 'human_review_pending' THEN 'pending'
                ELSE t.status
            END AS status,
            CASE
                WHEN t.source_type = 'naver_cafe'
                 AND EXISTS (
                     SELECT 1
                     FROM answer_draft d
                     WHERE d.ticket_id = t.ticket_id
                 )
                THEN TRUE
                ELSE FALSE
            END AS can_edit_draft,
            t.assignee_id,
            t.inquiry_created_at,
            u.nickname,
            u.email,
            u.user_status,
            u.last_login_at,
            latest_draft.draft_id,
            latest_draft.draft_text,
            latest_draft.created_at AS draft_created_at,
            latest_analysis.risk_level,
            latest_analysis.routing_target
        FROM qa_ticket t
        LEFT JOIN community_users u ON u.user_id = t.user_id
        LEFT JOIN LATERAL (
            SELECT draft_id, draft_text, created_at
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
        ORDER BY
            CASE WHEN latest_draft.draft_id IS NULL THEN 1 ELSE 0 END ASC,
            t.inquiry_created_at ASC NULLS FIRST,
            t.ticket_id ASC
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
            Json(
                {
                    "draft_id": draft_id,
                    "reviewer_id": reviewer_id,
                    "reason": reason,
                }
            ),
        ),
    )


def _draft_for_update(cur: Any, draft_id: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT draft_id, ticket_id, analysis_id, draft_text, created_at
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


_TERMINAL_STATUSES = {"closed", "resolved", "urgent_alert_pending", "workflow_running"}


def _ensure_ticket_reprocessable(ticket_id: int) -> None:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT status FROM qa_ticket WHERE ticket_id = %s", (ticket_id,))
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
            if row["status"] in _TERMINAL_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail=f"ticket {ticket_id} is already in terminal status: {row['status']}",
                )


def _ensure_draft_reprocessable(cur: Any, draft: dict[str, Any]) -> None:
    draft_id = int(draft["draft_id"])
    ticket_id = int(draft["ticket_id"])

    cur.execute(
        """
        SELECT status
        FROM qa_ticket
        WHERE ticket_id = %s
        FOR UPDATE
        """,
        (ticket_id,),
    )
    ticket = cur.fetchone()
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    if ticket["status"] in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"ticket {ticket_id} is not reprocessable in status: {ticket['status']}",
        )

    cur.execute(
        """
        SELECT draft_id
        FROM answer_draft
        WHERE ticket_id = %s
        ORDER BY created_at DESC NULLS LAST, draft_id DESC
        LIMIT 1
        """,
        (ticket_id,),
    )
    latest_draft = cur.fetchone()
    if latest_draft is None or int(latest_draft["draft_id"]) != draft_id:
        latest_draft_id = int(latest_draft["draft_id"]) if latest_draft is not None else None
        raise HTTPException(
            status_code=409,
            detail=f"draft {draft_id} is stale; latest draft is {latest_draft_id}",
        )

    cur.execute("SELECT response_id FROM final_response WHERE draft_id = %s LIMIT 1", (draft_id,))
    if cur.fetchone() is not None:
        raise HTTPException(status_code=409, detail=f"draft {draft_id} is already approved")


def _ensure_draft_saveable(cur: Any, draft: dict[str, Any], reviewer_id: str | None) -> None:
    if not reviewer_id:
        raise HTTPException(status_code=400, detail="reviewer_id is required to edit drafts")
    cur.execute(
        """
        SELECT source_type, status, assignee_id
        FROM qa_ticket
        WHERE ticket_id = %s
        """,
        (draft["ticket_id"],),
    )
    ticket = cur.fetchone()
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {draft['ticket_id']}")
    if ticket["status"] != "pending" or ticket["assignee_id"] != reviewer_id:
        raise HTTPException(
            status_code=409,
            detail="only the assigned reviewer can edit pending ticket drafts",
        )


def _ensure_draft_actionable(cur: Any, draft: dict[str, Any]) -> None:
    cur.execute(
        """
        SELECT source_type, status
        FROM qa_ticket
        WHERE ticket_id = %s
        """,
        (draft["ticket_id"],),
    )
    ticket = cur.fetchone()
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {draft['ticket_id']}")
    if ticket["source_type"] != "naver_cafe" or ticket["status"] not in ("open", "pending"):
        raise HTTPException(
            status_code=409,
            detail="only naver_cafe tickets can process drafts",
        )


def _start_ticket_edit(cur: Any, *, ticket_id: int, reviewer_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT ticket_id, source_type, status
        FROM qa_ticket
        WHERE ticket_id = %s
        FOR UPDATE
        """,
        (ticket_id,),
    )
    ticket = cur.fetchone()
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    if ticket["source_type"] != "naver_cafe" or ticket["status"] not in ("open", "pending"):
        raise HTTPException(
            status_code=409,
            detail="only naver_cafe tickets with a draft can start editing",
        )
    cur.execute(
        """
        UPDATE qa_ticket
        SET status = 'pending',
            assignee_id = %s
        WHERE ticket_id = %s
        RETURNING ticket_id, status, assignee_id
        """,
        (reviewer_id, ticket_id),
    )
    updated = cur.fetchone()
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
            "start_edit",
            "pending",
            Json({"reviewer_id": reviewer_id}),
        ),
    )
    return dict(updated)


def _resolve_ticket(cur: Any, *, ticket_id: int, reviewer_id: str | None, reason: str) -> None:
    cur.execute(
        """
        SELECT ticket_id, source_type, status
        FROM qa_ticket
        WHERE ticket_id = %s
        FOR UPDATE
        """,
        (ticket_id,),
    )
    ticket = cur.fetchone()
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    if ticket["source_type"] != "chatbot" or ticket["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail="only chatbot pending tickets can be resolved by email",
        )
    cur.execute("UPDATE qa_ticket SET status = 'resolved' WHERE ticket_id = %s", (ticket_id,))
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
            "ticket_resolved",
            "resolved",
            Json({"reviewer_id": reviewer_id, "reason": reason}),
        ),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}



@app.post("/auth/admin/login", response_model=AdminLoginResponse)
def admin_login(request: AdminLoginRequest) -> AdminLoginResponse:
    result = login_admin_with_credentials(request.login_id, request.password)
    return AdminLoginResponse(**result)


# [수정] 담당자 자동 할당 제거 — 할당은 티켓 선택 시 /assign 엔드포인트에서 처리
@app.post("/tickets/{ticket_id}/run-workflow", response_model=RunWorkflowResponse)
def run_workflow(ticket_id: int) -> RunWorkflowResponse:
    _ensure_ticket_reprocessable(ticket_id)
    try:
        result = run_workflow_step(ticket_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RunWorkflowResponse(
        ticket_id=ticket_id,
        status=result.get("status") or "unknown",
        final_answer=result.get("final_answer"),
        draft_id=result.get("draft_id"),
        analysis_id=result.get("analysis_id"),
        response_id=result.get("response_id"),
    )


# [추가] 티켓 담당자 명시적 할당 엔드포인트
@app.post("/tickets/{ticket_id}/assign")
def assign_ticket(ticket_id: int, request: AssignRequest) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT ticket_id FROM qa_ticket WHERE ticket_id = %s", (ticket_id,))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
            cur.execute(
                "UPDATE qa_ticket SET assignee_id = %s WHERE ticket_id = %s",
                (request.reviewer_id, ticket_id),
            )
    return {"ticket_id": ticket_id, "assignee_id": request.reviewer_id}


@app.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(ticket_id: int, request: ResolveTicketRequest) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _resolve_ticket(cur, ticket_id=ticket_id, reviewer_id=request.reviewer_id, reason=request.reason)
    return {"ticket_id": ticket_id, "status": "resolved"}


@app.post("/tickets/{ticket_id}/start-edit")
def start_edit_ticket(ticket_id: int, request: StartEditRequest) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            result = _start_ticket_edit(cur, ticket_id=ticket_id, reviewer_id=request.reviewer_id)
    return dict(result)


@app.get("/tickets")
def list_tickets(
    status: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    today_only: bool = Query(default=False),
    assignee_id: str | None = Query(default=None),  # [추가] 담당자 필터
) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _list_ticket_rows(
                cur,
                status=status,
                source_type=source_type,
                limit=limit,
                today_only=today_only,
                assignee_id=assignee_id,
            )

@app.get("/tickets/chatbot-pending")
def list_chatbot_pending_tickets(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _fetch_all(
                cur,
                """
                SELECT
                    t.ticket_id,
                    t.user_id,
                    t.title,
                    t.source_type,
                    t.status,
                    t.inquiry_created_at,
                    u.email,
                    u.nickname,
                    u.user_status,
                    u.last_login_at
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                WHERE t.source_type = 'chatbot'
                  AND t.status = 'pending'
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT %s
                """,
                (limit,),
            )


@app.get("/tickets/today")
def list_today_tickets(
    status: str | None = Query(default="open"),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _list_ticket_rows(cur, status=status, limit=limit, today_only=True)


def _fetch_ticket_sections(cur: Any, ticket_id: int) -> dict[str, Any]:
    analyses = _fetch_all(
        cur,
        "SELECT * FROM ticket_analysis WHERE ticket_id = %s ORDER BY analyzed_at DESC NULLS LAST, analysis_id DESC",
        (ticket_id,),
    )
    drafts = _fetch_all(
        cur,
        "SELECT * FROM answer_draft WHERE ticket_id = %s ORDER BY created_at DESC NULLS LAST, draft_id DESC",
        (ticket_id,),
    )
    draft_ids = [d["draft_id"] for d in drafts]
    evidence_docs: list[dict[str, Any]] = []
    safety_results: list[dict[str, Any]] = []
    if draft_ids:
        evidence_docs = _fetch_all(
            cur,
            "SELECT * FROM evidence_docs WHERE draft_id = ANY(%s) ORDER BY draft_id DESC, retrieval_rank ASC",
            (draft_ids,),
        )
        safety_results = _fetch_all(
            cur,
            "SELECT * FROM safety_results WHERE draft_id = ANY(%s) ORDER BY checked_at DESC NULLS LAST, safety_id DESC",
            (draft_ids,),
        )
    final_responses = _fetch_all(
        cur,
        "SELECT * FROM final_response WHERE ticket_id = %s ORDER BY created_at DESC NULLS LAST, response_id DESC",
        (ticket_id,),
    )
    notifications = _fetch_all(
        cur,
        "SELECT * FROM notification_logs WHERE ticket_id = %s ORDER BY sent_at DESC NULLS LAST, notification_id DESC",
        (ticket_id,),
    )
    review_logs = _fetch_all(
        cur,
        "SELECT * FROM admin_event_logs WHERE ticket_id = %s AND event_type = 'human_review' ORDER BY created_at DESC NULLS LAST, log_id DESC",
        (ticket_id,),
    )
    return {
        "analyses": analyses,
        "drafts": drafts,
        "evidence_docs": evidence_docs,
        "safety_results": safety_results,
        "final_responses": final_responses,
        "notifications": notifications,
        "review_logs": review_logs,
    }


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
                    a.account_status,
                    CASE
                        WHEN t.source_type = 'naver_cafe'
                         AND EXISTS (
                             SELECT 1
                             FROM answer_draft d
                             WHERE d.ticket_id = t.ticket_id
                         )
                        THEN TRUE
                        ELSE FALSE
                    END AS can_edit_draft
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN game_accounts a ON a.account_id = t.account_id
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            if ticket is None:
                raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
            sections = _fetch_ticket_sections(cur, ticket_id)
            if ticket.get("status") == "human_review_pending":
                ticket["status"] = "pending"
    return {"ticket": ticket, **sections}


@app.patch("/drafts/{draft_id}")
def edit_draft(draft_id: int, request: DraftEditRequest) -> ReviewActionResponse:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _draft_for_update(cur, draft_id)
            _ensure_draft_reprocessable(cur, draft)
            _ensure_draft_saveable(cur, draft, request.reviewer_id)
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="edited",
                reviewer_id=request.reviewer_id,
                reason=request.reason,
            )

    result = edit_existing_draft(draft_id, request.draft_text)
    return ReviewActionResponse(
        ticket_id=draft["ticket_id"],
        draft_id=draft_id,
        decision="edited",
        status=result.get("status") or "unknown",
        response_id=result.get("response_id"),
        next_draft_id=result.get("draft_id"),
    )


@app.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, request: ApproveDraftRequest) -> ReviewActionResponse:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _draft_for_update(cur, draft_id)
            _ensure_draft_reprocessable(cur, draft)
            _ensure_draft_actionable(cur, draft)
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="approved",
                reviewer_id=request.reviewer_id,
                reason=request.reason,
            )

    try:
        
        result = approve_existing_draft(draft_id, request.final_text or None)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReviewActionResponse(
        ticket_id=draft["ticket_id"],
        draft_id=draft_id,
        decision="approved",
        status=result.get("status") or "unknown",
        response_id=result.get("response_id"),
        next_draft_id=result.get("draft_id"),
    )


@app.post("/drafts/{draft_id}/regenerate")
def regenerate_draft(draft_id: int, request: RegenerateDraftRequest) -> ReviewActionResponse:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _draft_for_update(cur, draft_id)
            _ensure_draft_reprocessable(cur, draft)
            _ensure_draft_actionable(cur, draft)
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="regenerate",
                reviewer_id=request.reviewer_id,
                reason=request.reason,
            )

    try:
        result = regenerate_from_draft(draft_id, reason=request.reason)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReviewActionResponse(
        ticket_id=draft["ticket_id"],
        draft_id=draft_id,
        decision="regenerate",
        status=result.get("status") or "unknown",
        response_id=result.get("response_id"),
        next_draft_id=result.get("draft_id"),
    )


@app.post("/drafts/{draft_id}/reject")
def reject_draft(draft_id: int, request: RegenerateDraftRequest) -> ReviewActionResponse:
    return regenerate_draft(draft_id, request)


if _FRONTEND_STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_STATIC_DIR, html=True), name="cs_auto_frontend")
