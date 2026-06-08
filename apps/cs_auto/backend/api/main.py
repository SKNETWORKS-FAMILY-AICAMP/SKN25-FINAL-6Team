"""
프론트엔드에 보낼 api 전용 함수
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg.types.json import Json
from pydantic import BaseModel

from agents.answer_agent import regenerate_agent
from common.db.connection import db_connection
from utils.cafe.upload import build_cafe_comment_payload, record_cafe_upload_result, upload_comment_to_naver_cafe
from utils.login.admin_login import create_admin_session, revoke_admin_session, verify_admin_user_credentials


app = FastAPI(title="CS Auto API")

# 프론트와 API 사이의 핵심 연동 정책이다. 실제 라우트는 아래 함수들이 담당하지만,
# 테스트에서는 이 계약을 먼저 확인해 "초안까지만", "승인 시 resolved" 같은
# 운영 정책이 의도치 않게 바뀌지 않았는지 검증한다.
API_INTEGRATION_CONTRACT = {
    "regeneration_flow": "request_draft_regeneration -> regenerate_agent(ticket_id, regeneration_reason)",
    "draft_update_policy": "overwrite_answer_draft_text",
    "approval_policy": "insert_final_response_then_resolve_ticket",
    "detail_payload_sections": ["ticket", "evidence", "safety", "history", "operationLogs"],
    "latest_draft_order": "answer_draft.created_at DESC NULLS LAST, answer_draft.draft_id DESC",
}

_cors_origins = [
    origin.strip()
    for origin in os.environ.get("CS_AUTO_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AdminLoginRequest(BaseModel):
    """
    프론트엔드 로그인 폼에서 백엔드로 보내는 요청 모델.

    예상 내용:
    - login_id는 admin_users.login_id와 비교한다.
    - password는 password_hash 검증에만 사용하고 응답이나 로그에 남기지 않는다.
    """

    login_id: str
    password: str


class OperatorLogoutRequest(BaseModel):
    """
    프론트엔드 로그아웃 요청 모델.

    예상 내용:
    - admin_id 또는 session_id를 받아 현재 운영자 세션을 종료한다.
    - 토큰 기반 인증을 쓰면 token 식별자를 함께 받을 수 있다.
    """

    admin_id: int | None = None
    session_id: str | None = None


class DraftUpdateRequest(BaseModel):
    """
    프론트엔드에서 수정 완료한 답변 초안 요청 모델.

    예상 내용:
    - draft_id는 answer_draft.draft_id와 연결한다.
    - edited_text는 운영자가 textarea에서 수정한 답변 본문이다.
    - edit_reason은 운영자 수정 사유를 admin_event_logs.metadata에 남길 때 사용한다.
    """

    draft_id: int
    edited_text: str
    admin_id: int
    edit_reason: str | None = None


class DraftRegenerateRequest(BaseModel):
    """
    프론트엔드에서 답변 재생성을 요청할 때 보내는 요청 모델.

    예상 내용:
    - draft_id는 현재 보고 있는 최신 answer_draft를 가리킨다.
    - regeneration_reason은 agents.answer_agent.regenerate_agent 프롬프트에 전달한다.
    - admin_id는 재생성 요청 이력을 admin_event_logs에 남길 때 사용한다.
    """

    draft_id: int
    regeneration_reason: str
    admin_id: int


class DraftApproveRequest(BaseModel):
    """
    프론트엔드에서 답변 완료를 누를 때 보내는 승인 요청 모델.

    예상 내용:
    - draft_id는 승인 대상 초안이다.
    - final_text는 운영자가 최종 확정한 답변 본문이다.
    - edit_reason은 수정 후 승인한 경우 선택적으로 남긴다.
    """

    draft_id: int
    final_text: str
    admin_id: int
    edit_reason: str | None = None


class CafeCommentRequest(BaseModel):
    """
    최종 답변을 네이버 카페 댓글로 업로드할 때 보내는 요청 모델.

    예상 내용:
    - response_id는 final_response.response_id와 연결한다.
    - admin_id는 업로드를 수행한 운영자를 기록한다.
    """

    response_id: int
    admin_id: int


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _next_integer_id(cur: Any, table_name: str, id_column: str) -> int:
    cur.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS next_id FROM {table_name}")
    row = cur.fetchone()
    return int(row["next_id"])


def _ticket_id_from_frontend(ticket_id: int | str) -> int:
    return int(str(ticket_id).replace("TK-", ""))


def _format_datetime(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if hasattr(value, "strftime"):
        return value.strftime("%m-%d %H:%M")
    return str(value)


def _time_ago(value: Any) -> str:
    if value is None:
        return "-"
    now = datetime.now()
    delta = now - value.replace(tzinfo=None) if hasattr(value, "replace") else None
    if delta is None:
        return "-"
    minutes = max(int(delta.total_seconds() // 60), 0)
    if minutes < 60:
        return f"{minutes}분 전"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"
    return f"{hours // 24}일 전"


def _priority_label(row: dict[str, Any]) -> tuple[str, str]:
    risk = str(row.get("risk_level") or "").lower()
    has_response = row.get("response_id") is not None
    has_draft = row.get("draft_id") is not None
    has_assignee = row.get("assignee_admin_id") is not None
    if has_response:
        return "종료", "done"
    if risk in {"high", "critical", "1"}:
        return "긴급", "urgent"
    if has_assignee:
        return "검토 중", "review"
    if has_draft:
        return "대기", "pending"
    return "초안 없음", "none"


def _draft_status(row: dict[str, Any]) -> str:
    if row.get("response_id") is not None:
        return "approved"
    if row.get("draft_id") is not None:
        return "draft"
    return "none"


def _review_status(row: dict[str, Any]) -> str:
    if row.get("response_id") is not None:
        return "done"
    if row.get("assignee_admin_id") is not None:
        return "review"
    if row.get("draft_id") is not None:
        return "pending"
    return "waiting_draft"


def _status_text(row: dict[str, Any]) -> str:
    assignee = row.get("assignee_display_name") or row.get("assignee_login_id") or "미할당"
    if row.get("response_id") is not None:
        return "종료 처리되었습니다."
    if row.get("assignee_admin_id") is not None:
        return f"{assignee} 검토 중..."
    if row.get("draft_id") is not None:
        return "답변 초안 검토 대기"
    return "답변 초안 생성 대기"


def _write_admin_event_log(
    cur: Any,
    *,
    ticket_id: int | None,
    admin_id: int | None,
    event_type: str,
    status: str,
    metadata: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO admin_event_logs (
            ticket_id,
            node_name,
            event_type,
            status,
            metadata,
            actor_admin_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            ticket_id,
            "cs_auto_api",
            event_type,
            status,
            Json(metadata),
            admin_id,
        ),
    )


def get_cs_auto_api_contract() -> dict[str, object]:
    """CS 자동화 API와 답변생성 agent의 연동 계약을 반환한다.

    프론트엔드와 운영 API는 현재 별도 서비스 계층 없이 이 파일의 함수들을 직접
    사용한다. 그래서 재생성/수정/승인/상세 조회 정책이 코드 변경 중 흐려지지
    않도록 읽기 전용 계약으로 고정한다.
    """

    return {
        **API_INTEGRATION_CONTRACT,
        "regeneration_agent_function": "agents.answer_agent.regenerate_agent",
        "draft_update_side_effects": [
            "answer_draft.draft_text overwrite",
            "qa_ticket.status = human_review",
            "admin_event_logs event_type = draft_updated",
        ],
        "approval_side_effects": [
            "final_response insert",
            "qa_ticket.status = resolved",
            "admin_event_logs event_type = draft_approved",
        ],
        "frontend_detail_visibility": {
            "batch_draft_visible": True,
            "evidence_docs_visible": True,
            "safety_results_visible": True,
            "admin_history_visible": True,
            "operation_logs_visible": True,
        },
    }


def _ticket_list_sql(where_sql: str) -> str:
    """티켓 목록/상세가 공유하는 기본 조회 SQL을 만든다.

    최신 분석, 최신 초안, 최신 최종응답, 최신 safety를 모두 LATERAL로 붙여
    프론트가 ticket_id 하나만으로 현재 처리 맥락을 볼 수 있게 한다.
    chatbot pending 문의도 화면에 보여야 하므로 qa_ticket.source_type은 여기서
    제한하지 않고 호출부 필터가 필요한 경우에만 where_sql에 넣는다.
    """

    return f"""
        SELECT
            t.ticket_id,
            t.account_id,
            t.user_id,
            t.title,
            t.raw_query,
            t.source_type,
            t.status,
            t.assignee_admin_id,
            t.inquiry_created_at,
            t.session_id,
            t.responder_type,
            u.nickname,
            -- chatbot pending 문의는 상담원 화면에서 사용자 식별이 필요하므로
            -- email을 payload에 포함한다. 다만 로그 metadata에는 저장하지 않는다.
            u.email,
            ga.uid,
            au.login_id AS assignee_login_id,
            au.display_name AS assignee_display_name,
            latest_analysis.analysis_id,
            latest_analysis.category,
            latest_analysis.risk_level,
            latest_analysis.sentiment,
            latest_analysis.routing_target,
            latest_analysis.summary,
            latest_draft.draft_id,
            latest_draft.draft_text,
            latest_draft.created_at AS draft_created_at,
            latest_response.response_id,
            latest_response.final_text,
            latest_response.created_at AS response_created_at,
            latest_safety.retry_count,
            latest_safety.safety_action
        FROM qa_ticket t
        LEFT JOIN community_users u ON u.user_id = t.user_id
        LEFT JOIN game_accounts ga ON ga.account_id = t.account_id
        LEFT JOIN admin_users au ON au.admin_id = t.assignee_admin_id
        LEFT JOIN LATERAL (
            SELECT
                a.analysis_id,
                a.category,
                a.risk_level,
                a.sentiment,
                a.routing_target,
                a.summary,
                a.analyzed_at
            FROM ticket_analysis a
            WHERE a.ticket_id = t.ticket_id
            ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
            LIMIT 1
        ) latest_analysis ON TRUE
        LEFT JOIN LATERAL (
            SELECT d.draft_id, d.draft_text, d.created_at
            FROM answer_draft d
            WHERE d.ticket_id = t.ticket_id
            ORDER BY d.created_at DESC NULLS LAST, d.draft_id DESC
            LIMIT 1
        ) latest_draft ON TRUE
        LEFT JOIN LATERAL (
            SELECT fr.response_id, fr.final_text, fr.created_at
            FROM final_response fr
            WHERE fr.ticket_id = t.ticket_id
            ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
            LIMIT 1
        ) latest_response ON TRUE
        LEFT JOIN LATERAL (
            SELECT s.retry_count, s.safety_action
            FROM safety_results s
            WHERE s.draft_id = latest_draft.draft_id
            ORDER BY s.checked_at DESC NULLS LAST, s.safety_id DESC
            LIMIT 1
        ) latest_safety ON TRUE
        WHERE {where_sql}
    """


def validate_regeneration_limit(ticket_id: int) -> dict[str, object]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _fetch_one(
                cur,
                """
                SELECT COALESCE(MAX(s.retry_count), 0) AS retry_count
                FROM answer_draft d
                LEFT JOIN safety_results s ON s.draft_id = d.draft_id
                WHERE d.ticket_id = %s
                """,
                (ticket_id,),
            )

    retry_count = int(row.get("retry_count") or 0) if row else 0
    limit = int(os.environ.get("CS_AUTO_REGENERATION_LIMIT", "3"))
    return {
        "ticket_id": ticket_id,
        "retry_count": retry_count,
        "limit": limit,
        "can_regenerate": retry_count < limit,
    }


def create_cs_auto_api_app() -> object:
    """
    apps/cs_auto/frontend/cs_automation.html이 호출할 CS 자동화 API 앱을 생성한다.

    예상 내용:
    - FastAPI 인스턴스를 만들고 CORS 설정으로 프론트엔드 정적 HTML 접근을 허용한다.
    - register_cs_auto_routes를 호출해 로그인, 티켓 조회, 초안 수정, 재생성, 승인 API를 연결한다.
    - 실제 서버 실행은 uvicorn 또는 배포 설정에서 이 함수가 반환한 app을 사용한다.
    """

    return app


def register_cs_auto_routes(app: object) -> None:
    """
    프론트엔드 화면 이벤트와 백엔드 함수의 연결 경로를 등록한다.

    예상 내용:
    - POST /api/cs-auto/auth/login -> api_login_operator -> authenticate_operator
    - GET /api/cs-auto/tickets -> api_get_review_tickets -> fetch_review_ticket_cards
    - GET /api/cs-auto/tickets/{ticket_id} -> api_get_ticket_detail -> fetch_ticket_detail_for_frontend
    - PATCH /api/cs-auto/tickets/{ticket_id}/draft -> api_update_answer_draft -> update_draft_text_for_review
    - POST /api/cs-auto/tickets/{ticket_id}/draft/regenerate -> api_regenerate_answer_draft -> request_draft_regeneration
    - POST /api/cs-auto/tickets/{ticket_id}/draft/approve -> api_approve_answer_draft -> approve_draft_and_resolve_ticket
    - POST /api/cs-auto/tickets/{ticket_id}/cafe/comment -> api_upload_cafe_comment -> upload_final_answer_to_cafe
    """

    return None


@app.get("/health")
@app.get("/api/cs-auto/health")
def api_health_check() -> dict[str, object]:
    """
    프론트엔드가 백엔드 연결 상태를 확인하는 API 엔드포인트 함수.

    예상 내용:
    - 화면 최초 로드 시 백엔드 API가 살아 있는지 확인한다.
    - DB 연결, agent 준비 상태, 배치 실행 상태는 별도 상세 API에서 확인하도록 최소 응답만 반환한다.
    - 프론트엔드는 실패 시 로컬 더미 데이터 또는 오류 안내 상태로 전환할 수 있다.
    """

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS ticket_count FROM qa_ticket")
            row = cur.fetchone()

    return {
        "status": "ok",
        "database": "ok",
        "ticket_count": row["ticket_count"] if row else 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/auth/admin/login")
@app.post("/api/cs-auto/auth/login")
def api_login_operator(payload: AdminLoginRequest) -> dict[str, object]:
    """
    프론트엔드 로그인 폼의 reviewer ID와 비밀번호를 검증하는 API 엔드포인트 함수.

    예상 내용:
    - payload에서 login_id와 password를 받는다.
    - authenticate_operator를 호출해 admin_users 기준 운영자 여부를 확인한다.
    - 성공 시 admin_id, display_name, role, session 정보 또는 토큰 정보를 프론트엔드에 반환한다.
    - 실패 시 프론트엔드가 로그인 실패 메시지를 표시할 수 있는 응답 구조를 반환한다.
    """

    result = authenticate_operator(payload.login_id, payload.password)
    if not result.get("authenticated"):
        return {"ok": False, "message": "운영자 인증에 실패했습니다."}
    return jsonable_encoder(result)


@app.post("/auth/admin/logout")
@app.post("/api/cs-auto/auth/logout")
def api_logout_operator(payload: OperatorLogoutRequest) -> dict[str, object]:
    """
    프론트엔드 로그아웃 버튼과 연결되는 API 엔드포인트 함수.

    예상 내용:
    - 현재 운영자 세션 또는 토큰을 무효화한다.
    - admin_event_logs에 logout 이벤트를 남길 수 있게 actor_admin_id를 전달한다.
    - 프론트엔드는 성공 응답을 받은 뒤 currentReviewer와 선택된 티켓 상태를 초기화한다.
    """

    result = revoke_admin_session(payload.session_id, payload.admin_id)
    return jsonable_encoder(result)


@app.get("/tickets")
@app.get("/api/cs-auto/tickets")
def api_get_review_tickets(
    limit: int | None = None,
    status: str | None = None,
    assignee_admin_id: int | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    page: int | None = None,
) -> dict[str, object]:
    """
    프론트엔드 좌측 문의 목록과 검토 이력 목록을 채우는 API 엔드포인트 함수.

    예상 내용:
    - fetch_review_ticket_cards를 호출해 qa_ticket, ticket_analysis, answer_draft, safety_results의 최신 정보를 조합한다.
    - status, reviewer, category, risk_level, page, page_size 필터를 query로 받는다.
    - 프론트엔드의 ticket card에 필요한 id, title, user, createdAt, priorityLabel, statusText, draftStatus를 반환한다.
    """

    filters = {
        "limit": limit,
        "status": status,
        "assignee_admin_id": assignee_admin_id,
        "category": category,
        "risk_level": risk_level,
        "page": page,
    }
    tickets = fetch_review_ticket_cards(filters)
    return jsonable_encoder({"tickets": tickets, "count": len(tickets), "filters": filters})


@app.get("/tickets/{ticket_id}")
@app.get("/api/cs-auto/tickets/{ticket_id}")
def api_get_ticket_detail(ticket_id: int) -> dict[str, object]:
    """
    프론트엔드에서 특정 문의를 선택했을 때 상세 패널을 채우는 API 엔드포인트 함수.

    예상 내용:
    - fetch_ticket_detail_for_frontend를 호출해 문의 원문, 최신 분석, 답변 초안, 근거, safety, 최종 응답을 조회한다.
    - qa_ticket.ticket_id 기준으로 answer_draft, evidence_docs, safety_results, final_response를 연결한다.
    - 프론트엔드 textarea에는 answer_draft.draft_text 또는 운영자 수정 중인 값을 넣을 수 있게 반환한다.
    """

    return jsonable_encoder(fetch_ticket_detail_for_frontend(ticket_id))


@app.patch("/tickets/{ticket_id}/draft")
@app.patch("/api/cs-auto/tickets/{ticket_id}/draft")
@app.patch("/drafts/{draft_id}")
def api_update_answer_draft(ticket_id: int, payload: DraftUpdateRequest) -> dict[str, object]:
    """
    프론트엔드의 '수정 완료' 버튼과 연결되는 API 엔드포인트 함수.

    예상 내용:
    - payload에서 draft_id, edited_text, edit_reason, admin_id를 받는다.
    - update_draft_text_for_review를 호출해 수정 확정 상태를 기록한다.
    - answer_draft 원본을 덮어쓸지, final_response 전 단계의 검토 상태로만 둘지는 서비스 함수 정책을 따른다.
    - 프론트엔드에는 draftStatus=confirmed, status=review에 해당하는 표시 데이터를 반환한다.
    """

    result = update_draft_text_for_review(
        ticket_id=ticket_id,
        draft_id=payload.draft_id,
        edited_text=payload.edited_text,
        edit_reason=payload.edit_reason,
        admin_id=payload.admin_id,
    )
    return jsonable_encoder(result)


@app.post("/tickets/{ticket_id}/draft/regenerate")
@app.post("/api/cs-auto/tickets/{ticket_id}/draft/regenerate")
@app.post("/drafts/{draft_id}/regenerate")
def api_regenerate_answer_draft(ticket_id: int, payload: DraftRegenerateRequest) -> dict[str, object]:
    """
    프론트엔드의 '재생성' 요청과 연결되는 API 엔드포인트 함수.

    예상 내용:
    - payload에서 draft_id, regeneration_reason, admin_id를 받는다.
    - request_draft_regeneration을 호출하고 내부에서 agents.answer_agent.regenerate_agent로 연결한다.
    - safety_results.retry_count가 3 미만일 때만 새 초안 생성 요청을 진행한다.
    - 프론트엔드에는 새 draft_text, retry_count, draftStatus=draft, status=review를 반환한다.
    """

    result = request_draft_regeneration(
        ticket_id=ticket_id,
        draft_id=payload.draft_id,
        regeneration_reason=payload.regeneration_reason,
        admin_id=payload.admin_id,
    )
    return jsonable_encoder(result)


@app.post("/tickets/{ticket_id}/draft/approve")
@app.post("/api/cs-auto/tickets/{ticket_id}/draft/approve")
@app.post("/drafts/{draft_id}/approve")
def api_approve_answer_draft(ticket_id: int, payload: DraftApproveRequest) -> dict[str, object]:
    """
    프론트엔드의 '답변 완료' 버튼과 연결되는 API 엔드포인트 함수.

    예상 내용:
    - payload에서 draft_id, final_text, edit_reason, admin_id를 받는다.
    - approve_draft_and_resolve_ticket을 호출해 final_response 저장과 qa_ticket.status=resolved 갱신을 처리한다.
    - 필요하면 upload_final_answer_to_cafe를 별도 단계로 호출해 네이버 카페 댓글 업로드까지 연결한다.
    - 프론트엔드에는 draftStatus=approved, status=done, statusText, response_id를 반환한다.
    """

    result = approve_draft_and_resolve_ticket(
        ticket_id=ticket_id,
        draft_id=payload.draft_id,
        final_text=payload.final_text,
        edit_reason=payload.edit_reason,
        admin_id=payload.admin_id,
    )
    return jsonable_encoder(result)


@app.post("/tickets/{ticket_id}/cafe/comment")
@app.post("/api/cs-auto/tickets/{ticket_id}/cafe/comment")
def api_upload_cafe_comment(ticket_id: int, payload: CafeCommentRequest) -> dict[str, object]:
    """
    최종 승인된 답변을 네이버 카페 게시물 댓글로 업로드하는 API 엔드포인트 함수.

    예상 내용:
    - payload에서 response_id, admin_id, cafe_post_url 또는 source_id를 받는다.
    - upload_final_answer_to_cafe를 호출해 final_response.final_text를 카페 댓글로 전달한다.
    - 업로드 성공 또는 실패 결과를 notification_logs나 admin_event_logs에 남길 수 있게 반환한다.
    """

    result = upload_final_answer_to_cafe(
        ticket_id=ticket_id,
        response_id=payload.response_id,
        admin_id=payload.admin_id,
    )
    return jsonable_encoder(result)


def authenticate_operator(login_id: str, password: str) -> dict[str, object]:
    """
    admin_users 테이블 기준으로 운영자 로그인을 확인하는 서비스 함수.

    예상 내용:
    - apps.cs_auto.backend.utils.login.admin_login 쪽 검증 함수와 연결한다.
    - admin_users.login_id, password_hash, role, status를 확인한다.
    - 비밀번호 원문은 로그나 응답에 남기지 않는다.
    - 성공 시 프론트엔드가 currentReviewer로 사용할 display_name 또는 login_id를 반환한다.
    """

    admin_user = verify_admin_user_credentials(login_id, password)
    if not admin_user.get("authenticated"):
        return admin_user
    session = create_admin_session(admin_user)
    return {
        **admin_user,
        "session": session,
        "currentReviewer": session["display_name"] or session["login_id"],
    }


def fetch_review_ticket_cards(filters: dict[str, object]) -> list[dict[str, object]]:
    """
    프론트엔드 문의 카드 목록에 맞춘 조회 결과를 만든다.

    예상 내용:
    - qa_ticket.status가 open, analyzed, drafted, human_review, resolved인 문의를 화면 필터에 맞게 조회한다.
    - 최신 ticket_analysis는 analyzed_at DESC, analysis_id DESC 기준으로 1건만 붙인다.
    - 최신 answer_draft는 created_at DESC, draft_id DESC 기준으로 1건만 붙인다.
    - safety_results와 final_response 존재 여부를 draftStatus와 statusText로 변환한다.
    """

    limit = int(filters.get("limit") or os.environ.get("CS_AUTO_TICKET_LIMIT", "50"))
    page = max(int(filters.get("page") or 1), 1)
    offset = (page - 1) * limit
    clauses = ["TRUE"]
    params: list[Any] = []

    status = filters.get("status")
    if status:
        clauses.append("LOWER(COALESCE(t.status, '')) = LOWER(%s)")
        params.append(status)
    if filters.get("assignee_admin_id") is not None:
        clauses.append("t.assignee_admin_id = %s")
        params.append(filters["assignee_admin_id"])
    if filters.get("category"):
        clauses.append("LOWER(COALESCE(latest_analysis.category, '')) = LOWER(%s)")
        params.append(filters["category"])
    if filters.get("risk_level"):
        clauses.append("LOWER(COALESCE(latest_analysis.risk_level, '')) = LOWER(%s)")
        params.append(filters["risk_level"])

    params.extend([limit, offset])
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = _fetch_all(
                cur,
                f"""
                {_ticket_list_sql(" AND ".join(clauses))}
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            )

    return [build_frontend_ticket_payload(row) for row in rows]


def fetch_ticket_detail_for_frontend(ticket_id: int) -> dict[str, object]:
    """
    프론트엔드 상세 패널에 필요한 티켓 단위 전체 맥락을 만든다.

    예상 내용:
    - qa_ticket 원문과 계정 식별 정보를 조회한다.
    - ticket_analysis의 category, routing_target, risk_level, sentiment, summary를 붙인다.
    - answer_draft, evidence_docs, safety_results, final_response 최신 정보를 함께 반환한다.
    - payments, refunds, item_delivery_logs, gacha_logs 요약은 근거 탭 또는 운영 로그 영역에 제공한다.
    """

    numeric_ticket_id = _ticket_id_from_frontend(ticket_id)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            ticket_row = _fetch_one(
                cur,
                f"""
                {_ticket_list_sql("t.ticket_id = %s")}
                """,
                (numeric_ticket_id,),
            )
            if ticket_row is None:
                return {"ok": False, "message": "문의가 존재하지 않습니다.", "ticket_id": numeric_ticket_id}

            evidence_rows = _fetch_all(
                cur,
                """
                SELECT e.evidence_id, e.draft_id, e.source_type, e.source_id, e.evidence_text, e.relevance_score, e.retrieval_rank
                FROM evidence_docs e
                WHERE e.draft_id = %s
                ORDER BY e.retrieval_rank ASC NULLS LAST, e.evidence_id DESC
                """,
                (ticket_row["draft_id"],),
            ) if ticket_row.get("draft_id") is not None else []
            safety_rows = _fetch_all(
                cur,
                """
                SELECT safety_id, draft_id, hallucination_score, toxicity_score, policy_violation_score,
                       factuality_score, checked_at, safety_action, safety_reason, retry_count
                FROM safety_results
                WHERE draft_id = %s
                ORDER BY checked_at DESC NULLS LAST, safety_id DESC
                """,
                (ticket_row["draft_id"],),
            ) if ticket_row.get("draft_id") is not None else []
            event_rows = _fetch_all(
                cur,
                """
                SELECT l.log_id, l.event_type, l.status, l.metadata, l.created_at, au.display_name, au.login_id
                FROM admin_event_logs l
                LEFT JOIN admin_users au ON au.admin_id = l.actor_admin_id
                WHERE l.ticket_id = %s
                ORDER BY l.created_at DESC NULLS LAST, l.log_id DESC
                LIMIT 30
                """,
                (numeric_ticket_id,),
            )
            operation_logs = {
                "payments": _fetch_all(
                    cur,
                    """
                    SELECT p.payment_id, p.product_name, p.product_type, p.amount, p.currency,
                           p.payment_method, p.payment_status, p.paid_at
                    FROM payments p
                    WHERE p.account_id = %s
                    ORDER BY p.paid_at DESC NULLS LAST, p.payment_id DESC
                    LIMIT 20
                    """,
                    (ticket_row["account_id"],),
                ) if ticket_row.get("account_id") is not None else [],
                "refunds": _fetch_all(
                    cur,
                    """
                    SELECT r.refund_id, r.payment_id, r.refund_status, r.requested_at, r.processed_at
                    FROM refunds r
                    JOIN payments p ON p.payment_id = r.payment_id
                    WHERE p.account_id = %s
                    ORDER BY r.requested_at DESC NULLS LAST, r.refund_id DESC
                    LIMIT 20
                    """,
                    (ticket_row["account_id"],),
                ) if ticket_row.get("account_id") is not None else [],
                "item_delivery_logs": _fetch_all(
                    cur,
                    """
                    SELECT delivery_id, payment_id, item_name, quantity, delivery_status, expected_at, delivered_at
                    FROM item_delivery_logs
                    WHERE account_id = %s
                    ORDER BY expected_at DESC NULLS LAST, delivery_id DESC
                    LIMIT 20
                    """,
                    (ticket_row["account_id"],),
                ) if ticket_row.get("account_id") is not None else [],
                "gacha_logs": _fetch_all(
                    cur,
                    """
                    SELECT gacha_id, banner_name, item_name, item_type, rarity, pity_count, pulled_at
                    FROM gacha_logs
                    WHERE account_id = %s
                    ORDER BY pulled_at DESC NULLS LAST, gacha_id DESC
                    LIMIT 20
                    """,
                    (ticket_row["account_id"],),
                ) if ticket_row.get("account_id") is not None else [],
            }

    return {
        "ticket": build_frontend_ticket_payload(ticket_row),
        "evidence": [
            {
                "rank": row.get("retrieval_rank"),
                "source": f"{row.get('source_type') or '-'} / {row.get('source_id') or '-'}",
                "body": row.get("evidence_text"),
                "score": row.get("relevance_score"),
            }
            for row in evidence_rows
        ],
        "safety": safety_rows,
        "history": build_frontend_history_payload(event_rows),
        "operationLogs": operation_logs,
    }


def update_draft_text_for_review(
    ticket_id: int,
    draft_id: int,
    edited_text: str,
    edit_reason: str | None,
    admin_id: int,
) -> dict[str, object]:
    """
    운영자가 수정 완료한 답변 초안을 검토 상태로 기록하는 서비스 함수.

    예상 내용:
    - answer_draft 원본은 AI 생성 초안으로 보존하고, 수정본은 승인 전 임시 상태 또는 이벤트 로그에 남기는 정책을 검토한다.
    - 별도 수정 이력 테이블이 없으므로 admin_event_logs.metadata에 draft_id, edited_text 요약, edit_reason을 남길 수 있다.
    - qa_ticket.status는 resolved가 아니라 review 또는 human_review 단계로 유지한다.
    - 이후 approve_draft_and_resolve_ticket이 final_response.final_text에 최종 수정본을 저장한다.
    """

    numeric_ticket_id = _ticket_id_from_frontend(ticket_id)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE answer_draft
                SET draft_text = %s
                WHERE draft_id = %s
                  AND ticket_id = %s
                RETURNING draft_id, ticket_id, draft_text, created_at
                """,
                (edited_text, draft_id, numeric_ticket_id),
            )
            draft_row = cur.fetchone()
            if draft_row is None:
                return {"ok": False, "message": "수정할 답변 초안이 존재하지 않습니다.", "ticket_id": numeric_ticket_id, "draft_id": draft_id}

            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s,
                    assignee_admin_id = %s
                WHERE ticket_id = %s
                """,
                ("human_review", admin_id, numeric_ticket_id),
            )
            _write_admin_event_log(
                cur,
                ticket_id=numeric_ticket_id,
                admin_id=admin_id,
                event_type="draft_updated",
                status="success",
                metadata={
                    "draft_id": draft_id,
                    "edit_reason": edit_reason,
                    "edited_text_length": len(edited_text),
                },
            )

    detail = fetch_ticket_detail_for_frontend(numeric_ticket_id)
    return {"ticket": detail["ticket"], "draft": dict(draft_row), "history": detail["history"]}


def request_draft_regeneration(
    ticket_id: int,
    draft_id: int,
    regeneration_reason: str,
    admin_id: int,
) -> dict[str, object]:
    """
    운영자 재생성 요청을 answer_agent.regenerate_agent 흐름으로 연결하는 서비스 함수.

    예상 내용:
    - 기존 draft_id가 해당 ticket_id에 속하는지 먼저 검증한다.
    - agents.answer_agent.regenerate_agent에 ticket_id와 regeneration_reason을 전달한다.
    - agent가 생성한 새 초안 id와 재생성 사유를 admin_event_logs에 기록한다.
    - 프론트가 textarea를 즉시 갱신할 수 있도록 새 draft payload를 반환한다.
    """

    numeric_ticket_id = _ticket_id_from_frontend(ticket_id)
    limit_payload = validate_regeneration_limit(numeric_ticket_id)
    if not limit_payload["can_regenerate"]:
        return {"ok": False, "message": "재생성 가능 횟수를 초과했습니다.", **limit_payload}

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            current_draft = _fetch_one(
                cur,
                """
                SELECT draft_id, ticket_id, analysis_id, draft_text
                FROM answer_draft
                WHERE draft_id = %s
                  AND ticket_id = %s
                """,
                (draft_id, numeric_ticket_id),
            )
            if current_draft is None:
                return {"ok": False, "message": "재생성할 답변 초안이 존재하지 않습니다.", "ticket_id": numeric_ticket_id, "draft_id": draft_id}

    agent_result = regenerate_agent(ticket_id=numeric_ticket_id, regeneration_reason=regeneration_reason)
    if agent_result is None:
        return {"ok": False, "message": "재생성 초안 생성에 실패했습니다.", **limit_payload}

    new_draft = dict(agent_result["draft"])
    retry_count = int(agent_result["retry_count"])

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s,
                    assignee_admin_id = %s
                WHERE ticket_id = %s
                """,
                ("human_review", admin_id, numeric_ticket_id),
            )
            _write_admin_event_log(
                cur,
                ticket_id=numeric_ticket_id,
                admin_id=admin_id,
                event_type="draft_regenerated",
                status="success",
                metadata={
                    "previous_draft_id": draft_id,
                    "new_draft_id": new_draft["draft_id"],
                    "regeneration_reason_length": len(regeneration_reason),
                    "retry_count": retry_count,
                },
            )

    detail = fetch_ticket_detail_for_frontend(numeric_ticket_id)
    return {"ticket": detail["ticket"], "draft": new_draft, "retry_count": retry_count}


def approve_draft_and_resolve_ticket(
    ticket_id: int,
    draft_id: int,
    final_text: str,
    edit_reason: str | None,
    admin_id: int,
) -> dict[str, object]:
    """
    운영자 승인 답변을 final_response에 저장하고 qa_ticket.status를 resolved로 바꾸는 서비스 함수.

    예상 내용:
    - agents.answer_agent.save_final_response_after_approval을 호출한다.
    - final_response 저장과 agents.answer_agent.mark_ticket_resolved_after_final_response를 같은 DB 트랜잭션으로 묶는다.
    - edit_reason이 있으면 admin_event_logs.metadata에 수정 승인 사유로 남긴다.
    - 프론트엔드의 status=done, draftStatus=approved, statusText 표시값을 만들 수 있게 반환한다.
    """

    numeric_ticket_id = _ticket_id_from_frontend(ticket_id)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            draft_row = _fetch_one(
                cur,
                """
                SELECT draft_id, ticket_id
                FROM answer_draft
                WHERE draft_id = %s
                  AND ticket_id = %s
                """,
                (draft_id, numeric_ticket_id),
            )
            if draft_row is None:
                return {"ok": False, "message": "승인할 답변 초안이 존재하지 않습니다.", "ticket_id": numeric_ticket_id, "draft_id": draft_id}

            response_id = _next_integer_id(cur, "final_response", "response_id")
            cur.execute(
                """
                INSERT INTO final_response (
                    response_id,
                    ticket_id,
                    draft_id,
                    final_text,
                    safety_action,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING response_id, ticket_id, draft_id, final_text, safety_action, created_at
                """,
                (response_id, numeric_ticket_id, draft_id, final_text, "approved_by_operator"),
            )
            response_row = cur.fetchone()
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s,
                    assignee_admin_id = %s
                WHERE ticket_id = %s
                """,
                ("resolved", admin_id, numeric_ticket_id),
            )
            _write_admin_event_log(
                cur,
                ticket_id=numeric_ticket_id,
                admin_id=admin_id,
                event_type="draft_approved",
                status="success",
                metadata={
                    "draft_id": draft_id,
                    "response_id": response_id,
                    "edit_reason": edit_reason,
                    "final_text_length": len(final_text),
                },
            )

    detail = fetch_ticket_detail_for_frontend(numeric_ticket_id)
    return {"ticket": detail["ticket"], "response": dict(response_row)}


def upload_final_answer_to_cafe(
    ticket_id: int,
    response_id: int,
    admin_id: int,
) -> dict[str, object]:
    """
    final_response에 저장된 최종 답변을 네이버 카페 댓글 업로드 함수로 연결한다.

    예상 내용:
    - apps.cs_auto.backend.utils.cafe.upload 쪽 업로드 함수를 호출한다.
    - qa_ticket.source_type과 원문 출처가 naver_cafe인지 확인한다.
    - 업로드 성공 시 notification_logs 또는 admin_event_logs에 cafe_comment_uploaded 이벤트를 남긴다.
    - 업로드 실패 시 final_response와 qa_ticket.status는 유지하고 재시도 가능한 결과를 반환한다.
    """

    payload = build_cafe_comment_payload(ticket_id, response_id)
    upload_result = upload_comment_to_naver_cafe(payload)
    result = record_cafe_upload_result(ticket_id, response_id, upload_result)
    with db_connection() as conn:
        with conn.cursor() as cur:
            _write_admin_event_log(
                cur,
                ticket_id=ticket_id,
                admin_id=admin_id,
                event_type="cafe_comment_requested",
                status=str(result.get("status") or "unknown"),
                metadata={"response_id": response_id, "upload_result": upload_result},
            )
    return result


def build_frontend_ticket_payload(ticket_row: dict[str, object]) -> dict[str, object]:
    """
    DB 조회 결과를 cs_automation.html의 ticket 객체 형태로 변환한다.

    예상 내용:
    - ticket_id는 id로, qa_ticket.title은 title로, raw_query는 detail 또는 rawQuery로 매핑한다.
    - ticket_analysis.risk_level과 routing_target으로 priorityTone, priorityLabel을 만든다.
    - answer_draft 존재 여부와 safety_results 상태로 draftStatus를 만든다.
    - final_response가 있거나 qa_ticket.status가 resolved이면 프론트엔드 status를 done으로 변환한다.
    """

    priority_label, priority_tone = _priority_label(ticket_row)
    review_status = _review_status(ticket_row)
    draft_status = _draft_status(ticket_row)
    assignee = ticket_row.get("assignee_display_name") or ticket_row.get("assignee_login_id") or "미할당"
    risk_level = str(ticket_row.get("risk_level") or "LOW").upper()
    retry_count = int(ticket_row.get("retry_count") or 0)
    regen_limit = int(os.environ.get("CS_AUTO_REGENERATION_LIMIT", "3"))
    draft_text = ticket_row.get("draft_text") or ticket_row.get("final_text") or ""

    return {
        "id": f"TK-{ticket_row.get('ticket_id')}",
        "ticketId": ticket_row.get("ticket_id"),
        "draftId": ticket_row.get("draft_id"),
        "responseId": ticket_row.get("response_id"),
        "priorityLabel": priority_label,
        "priorityTone": priority_tone,
        "level": risk_level,
        "channel": ticket_row.get("source_type") or "-",
        "channelIcon": "brand-blogger" if ticket_row.get("source_type") == "naver_cafe" else "mail",
        "category": ticket_row.get("category") or "미분류",
        "status": review_status,
        "title": ticket_row.get("title") or "제목 없음",
        "assignee": assignee,
        "assigneeAdminId": ticket_row.get("assignee_admin_id"),
        "statusText": _status_text(ticket_row),
        "timeAgo": _time_ago(ticket_row.get("inquiry_created_at")),
        "nickname": ticket_row.get("nickname") or "-",
        # 프론트는 chatbot + pending 문의에서 이메일을 보여줘야 한다.
        # answer_agent 로그에는 email을 남기지 않지만, 상담원 화면 payload에는 포함한다.
        "userEmail": ticket_row.get("email") or "-",
        "email": ticket_row.get("email") or "-",
        "accountId": ticket_row.get("uid") or ticket_row.get("account_id"),
        "createdAt": _format_datetime(ticket_row.get("inquiry_created_at")),
        "body": ticket_row.get("raw_query") or "",
        "rawQuery": ticket_row.get("raw_query") or "",
        "aiSummary": ticket_row.get("summary") or "",
        "route": ticket_row.get("routing_target") or "-",
        "direction": ticket_row.get("routing_target") or "-",
        "risk": risk_level,
        "sentiment": ticket_row.get("sentiment") or "-",
        "draft": draft_text,
        "finalText": ticket_row.get("final_text"),
        "draftStatus": draft_status,
        "isDraftEditing": False,
        "regenCount": retry_count,
        "regenLimit": regen_limit,
        "lastGeneratedAt": _format_datetime(ticket_row.get("draft_created_at")),
        "sourceType": ticket_row.get("source_type"),
        # build_frontend_ticket_payload의 status는 화면 표시용 review status로 변환된다.
        # 원본 qa_ticket.status가 필요한 chatbot pending 분기를 위해 별도 필드로 보존한다.
        "rawStatus": ticket_row.get("status"),
        "safetyAction": ticket_row.get("safety_action"),
    }


def build_frontend_history_payload(event_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    admin_event_logs 조회 결과를 프론트엔드 검토 이력 리스트 형태로 변환한다.

    예상 내용:
    - event_type과 status를 decision, tone으로 매핑한다.
    - actor_admin_id 또는 display_name을 reviewer로 매핑한다.
    - metadata에 있는 edit_reason, regeneration_reason_length, response_id를 reason 문구로 정리한다.
    - created_at은 프론트엔드 표시용 시간 문자열로 변환한다.
    """

    history: list[dict[str, object]] = []
    for row in event_rows:
        metadata = row.get("metadata") or {}
        event_type = str(row.get("event_type") or "")
        status = str(row.get("status") or "")
        decision = {
            "draft_updated": "수정",
            "draft_regenerated": "재생성",
            "draft_approved": "승인",
            "cafe_comment_requested": "카페 업로드",
            "login": "로그인",
            "logout": "로그아웃",
        }.get(event_type, event_type or "이벤트")
        tone = "done" if status == "success" else "pending"
        reason = (
            metadata.get("edit_reason")
            or (f"재생성 요청 길이 {metadata.get('regeneration_reason_length')}자" if metadata.get("regeneration_reason_length") is not None else None)
            or metadata.get("reason")
            or f"{decision} 처리"
        )
        history.append(
            {
                "decision": decision,
                "tone": tone,
                "reviewer": row.get("display_name") or row.get("login_id") or "system",
                "reason": reason,
                "time": _format_datetime(row.get("created_at")),
            }
        )
    return history
