"""FastAPI endpoints for the operation workflow and human review actions."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from common.observability.langsmith import configure_langsmith

configure_langsmith("operation")

from common.db.connection import db_connection
from service.account_service import login_with_credentials
from workflow import OperationState, build_operation_graph
from workflow.state import HumanReviewResult


app = FastAPI(title="Operation Review API", version="2.0.0")


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


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    server_region: str = Field(min_length=1)


class LoginResponse(BaseModel):
    login_success: bool
    user_id: int | None = None
    account_id: int | None = None
    game_id: str = ""
    email: str = ""
    server_region: str = ""
    nickname: str | None = None
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


def _ticket_list_where(*, status: str | None, today_only: bool, assignee_id: str | None = None) -> tuple[str, list[Any]]:
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
    # [추가] 담당자 필터 — 할당된 검토 탭에서 사용
    if assignee_id:
        clauses.append("t.assignee_id = %s")
        params.append(assignee_id)
    if not clauses:
        return "", params
    return f"WHERE {' AND '.join(clauses)}", params


# [추가] assignee_id 파라미터 및 SELECT 컬럼 추가
def _list_ticket_rows(cur: Any, *, status: str | None, limit: int, today_only: bool = False, assignee_id: str | None = None) -> list[dict[str, Any]]:
    where_sql, params = _ticket_list_where(status=status, today_only=today_only, assignee_id=assignee_id)
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
            t.assignee_id,
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


_TERMINAL_STATUSES = {"closed", "urgent_alert_pending"}


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


def _run_graph(state: OperationState, *, ticket_id: int) -> dict[str, Any]:
    graph = build_operation_graph()
    return graph.invoke(
        state,
        config={
            "run_name": f"operation-workflow-{ticket_id}",
            "metadata": {"ticket_id": ticket_id, "workflow": "operation"},
        },
    )


def _human_review_state(
    *,
    ticket_id: int,
    decision: Literal["approved", "regenerate", "edit"],
    reason: str,
    edited_answer: str | None = None,
) -> OperationState:
    review = HumanReviewResult(decision=decision, reason=reason, edited_answer=edited_answer)
    return OperationState(
        ticket_id=str(ticket_id),
        approval_route="human_review",
        human_decision=decision,
        human_review=review,
        edited_answer=edited_answer,
        metadata={"review_reason": reason},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    result = login_with_credentials(request.email, request.password, request.server_region)
    return LoginResponse(**result)


# [수정] 담당자 자동 할당 제거 — 할당은 티켓 선택 시 /assign 엔드포인트에서 처리
@app.post("/tickets/{ticket_id}/run-workflow", response_model=RunWorkflowResponse)
def run_workflow(ticket_id: int) -> RunWorkflowResponse:
    _ensure_ticket_reprocessable(ticket_id)
    result = _run_graph(OperationState(ticket_id=str(ticket_id)), ticket_id=ticket_id)
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


@app.get("/tickets")
def list_tickets(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    today_only: bool = Query(default=False),
    assignee_id: str | None = Query(default=None),  # [추가] 담당자 필터
) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _list_ticket_rows(cur, status=status, limit=limit, today_only=today_only, assignee_id=assignee_id)


@app.get("/tickets/today")
def list_today_tickets(
    status: str | None = Query(default="pending"),
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
                    a.account_status
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN game_accounts a ON a.account_id = t.account_id
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            sections = _fetch_ticket_sections(cur, ticket_id)
    return {"ticket": ticket, **sections}


@app.patch("/drafts/{draft_id}")
def edit_draft(draft_id: int, request: DraftEditRequest) -> ReviewActionResponse:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _draft_for_update(cur, draft_id)
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="edited",
                reviewer_id=request.reviewer_id,
                reason=request.reason,
            )

    result = _run_graph(
        _human_review_state(
            ticket_id=draft["ticket_id"],
            decision="edit",
            reason=request.reason,
            edited_answer=request.draft_text,
        ),
        ticket_id=draft["ticket_id"],
    )
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
            cur.execute(
                "SELECT response_id FROM final_response WHERE draft_id = %s LIMIT 1",
                (draft_id,),
            )
            if cur.fetchone() is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"draft {draft_id} is already approved",
                )
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="approved",
                reviewer_id=request.reviewer_id,
                reason=request.reason,
            )

    edited_answer = request.final_text or None
    result = _run_graph(
        _human_review_state(
            ticket_id=draft["ticket_id"],
            decision="approved",
            reason=request.reason,
            edited_answer=edited_answer,
        ),
        ticket_id=draft["ticket_id"],
    )
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
            _insert_review_log(
                cur,
                ticket_id=draft["ticket_id"],
                draft_id=draft_id,
                decision="regenerate",
                reviewer_id=request.reviewer_id,
                reason=request.reason,
            )

    result = _run_graph(
        _human_review_state(
            ticket_id=draft["ticket_id"],
            decision="regenerate",
            reason=request.reason,
        ),
        ticket_id=draft["ticket_id"],
    )
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
    result = regenerate_draft(draft_id, request)
    result.run_workflow_url = f"/tickets/{result.ticket_id}/run-workflow"
    return result
