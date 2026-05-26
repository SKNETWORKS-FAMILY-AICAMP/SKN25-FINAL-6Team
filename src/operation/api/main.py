"""FastAPI endpoints for operation ticket review and answer approval."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from src.common.observability.langsmith import configure_langsmith

configure_langsmith("operation")

from src.common.db.connection import db_connection
from src.operation.workflow import OperationState, build_operation_graph


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
    run_workflow_url: str | None = None


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    """psycopg dict_row 결과를 일반 dict로 변환합니다. None 행은 None을 반환합니다."""
    return dict(row) if row is not None else None


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    """단일 행 SELECT를 실행하고 dict 또는 None을 반환합니다."""
    cur.execute(sql, params)
    return _row_to_dict(cur.fetchone())


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """다중 행 SELECT를 실행하고 dict 목록을 반환합니다."""
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _ticket_list_where(
    *,
    status: str | None,
    today_only: bool,
) -> tuple[str, list[Any]]:
    """status·today_only 조건을 WHERE 절 문자열과 파라미터 목록으로 변환합니다.

    조건이 없으면 빈 문자열을 반환해 _list_ticket_rows의 f-string에 그대로 삽입됩니다.
    """
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
    """qa_ticket 목록을 status·today_only 조건으로 조회합니다.

    LATERAL 서브쿼리로 최신 draft_id와 risk_level/routing_target을 함께 반환해
    목록 화면에서 추가 조회 없이 필요한 메타데이터를 제공합니다.
    """
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
    """검수 결정(approved/rejected/edited)을 admin_event_logs에 기록합니다.

    event_type='human_review'로 고정해 get_ticket_detail에서 검수 이력만 필터링할 수 있게 합니다.
    """
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
    """answer_draft 행을 FOR UPDATE 잠금과 함께 조회합니다.

    수정·승인·반려 API가 동시에 같은 draft를 변경하는 것을 방지합니다.
    존재하지 않는 draft_id이면 404를 반환합니다.
    """
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


# closed: 최종 응답이 발행된 종료 티켓 / urgent_alert_pending: 긴급 알림 대기 상태
# 두 상태 모두 워크플로우를 재실행해도 의미 없는 최종 상태이므로 409로 차단한다
_TERMINAL_STATUSES = {"closed", "urgent_alert_pending"}


class RunWorkflowResponse(BaseModel):
    ticket_id: int
    status: str
    final_answer: str | None = None
    draft_id: int | None = None
    analysis_id: int | None = None
    response_id: int | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tickets/{ticket_id}/run-workflow", response_model=RunWorkflowResponse)
def run_workflow(ticket_id: int) -> RunWorkflowResponse:
    """워크플로우 그래프를 실행해 티켓의 답변 초안을 생성합니다.

    이미 closed 또는 urgent_alert_pending 상태인 티켓은 재실행하지 않습니다.
    """
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

    graph = build_operation_graph()
    result = graph.invoke(
        OperationState(ticket_id=str(ticket_id)),
        # LangSmith 트레이스 식별자: run_name으로 티켓별 실행을 구분하고
        # metadata로 ticket_id를 필터 키로 사용할 수 있게 한다
        config={
            "run_name": f"operation-workflow-{ticket_id}",
            "metadata": {"ticket_id": ticket_id, "workflow": "operation"},
        },
    )

    return RunWorkflowResponse(
        ticket_id=ticket_id,
        status=result.get("status") or "unknown",
        final_answer=result.get("final_answer"),
        draft_id=result.get("draft_id"),
        analysis_id=result.get("analysis_id"),
        response_id=result.get("response_id"),
    )


@app.get("/tickets")
def list_tickets(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    today_only: bool = Query(default=False),
) -> list[dict[str, Any]]:
    """qa_ticket 목록을 status·today_only 조건으로 반환합니다.

    status 미지정이면 전체 상태를 조회합니다.
    """
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


def _fetch_ticket_sections(cur: Any, ticket_id: int) -> dict[str, Any]:
    """api_spec.md GET /tickets/{ticket_id} 응답 필드별 관련 테이블을 일괄 조회합니다."""
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
    """티켓 상세 정보와 관련 데이터(분석·초안·근거·안전성·최종응답·알림·검수 이력)를 반환합니다.

    ticket 행은 community_users, game_accounts와 LEFT JOIN해 사용자·계정 정보를 함께 제공합니다.
    """
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
    """답변 초안 텍스트를 수정하고 검수 이력에 edited 결정을 기록합니다."""
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
    """초안을 승인해 final_response에 저장하고 티켓 상태를 closed로 갱신합니다.

    이미 승인된 초안(final_response 행이 존재)을 재승인하면 409를 반환합니다.
    """
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft = _draft_for_update(cur, draft_id)
            cur.execute(
                "SELECT response_id FROM final_response WHERE draft_id = %s LIMIT 1",
                (draft_id,),
            )
            if cur.fetchone() is not None:
                raise HTTPException(status_code=409, detail=f"draft {draft_id} is already approved")
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
    """초안을 반려하고 티켓 상태를 pending으로 되돌립니다.

    반환값의 run_workflow_url을 사용해 워크플로우를 재실행할 수 있습니다.
    """
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
        run_workflow_url=f"/tickets/{draft['ticket_id']}/run-workflow",
    )
