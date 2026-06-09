"""
CS Auto API route skeletons.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel
from api.services.load_ticket import get_review_tickets, get_ticket_detail, run_load_ticket
from api.services.draft_actions import update_answer_draft as update_answer_draft_service

# 로그인 api 구현
from utils.login.admin_login import create_admin_session, revoke_admin_session, verify_admin_user_credentials


app = FastAPI(title="CS Auto API")


class AdminLoginRequest(BaseModel):
    login_id: str
    password: str


class OperatorLogoutRequest(BaseModel):
    admin_id: int | None = None
    session_id: str | None = None


class DraftUpdateRequest(BaseModel):
    draft_id: int
    edited_text: str
    admin_id: int
    edit_reason: str | None = None


class DraftRegenerateRequest(BaseModel):
    draft_id: int
    regeneration_reason: str
    admin_id: int


class DraftApproveRequest(BaseModel):
    draft_id: int
    final_text: str
    admin_id: int
    edit_reason: str | None = None



@app.get("/health")
@app.get("/api/cs-auto/health")
def api_health_check() -> dict[str, object]:
    return {"status": "ok"}
# ---------------------------------------------------------------------------
# 문의 보이는 APIs
# ---------------------------------------------------------------------------

@app.get("/api/cs-auto/tickets")
def api_get_review_tickets(
    limit: int | None = None,
    status: str | None = None,
    assignee_admin_id: int | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    page: int | None = None,
) -> dict[str, object]:
    return get_review_tickets(
        limit=limit,
        status=status,
        assignee_admin_id=assignee_admin_id,
        category=category,
        risk_level=risk_level,
        page=page,
    )


@app.get("/api/cs-auto/tickets/{ticket_id}")
def api_get_ticket_detail(ticket_id: int) -> dict[str, object]:
    return get_ticket_detail(ticket_id)




# ---------------------------------------------------------------------------
# Login/Logout APIs
# ---------------------------------------------------------------------------
@app.post("/api/cs-auto/auth/login")
def api_login_operator(payload: AdminLoginRequest) -> dict[str, object]:
    # apps\cs_auto\backend\utils\login\admin_login.py에서 구현한 함수.
    admin_user = verify_admin_user_credentials(payload.login_id, payload.password)
    if not admin_user.get("authenticated"):
        return {"ok": False, "message": "운영자 인증에 실패했습니다."}
    
    # apps\cs_auto\backend\utils\login\admin_login.py에서 구현한 함수.
    session = create_admin_session(admin_user)
    return {
        **admin_user,
        "session": session,
        "currentReviewer": session["display_name"] or session["login_id"],
    }


@app.post("/api/cs-auto/auth/logout")
def api_logout_operator(payload: OperatorLogoutRequest) -> dict[str, object]:
    return revoke_admin_session(payload.session_id, payload.admin_id)



# ---------------------------------------------------------------------------
# 답변 초안 관련 APIs
# ---------------------------------------------------------------------------

# 답변 초안 수정 api
@app.patch("/api/cs-auto/tickets/{ticket_id}/draft")
def api_update_answer_draft(ticket_id: int, payload: DraftUpdateRequest) -> dict[str, object]:
    result = update_answer_draft_service(
        ticket_id=ticket_id,
        draft_id=payload.draft_id,
        edited_text=payload.edited_text,
        admin_id=payload.admin_id,
        edit_reason=payload.edit_reason,
    )
    if result.get("ok") is False:
        return result
    return {"ok": True, "ticket": build_frontend_ticket_payload(result.get("ticket"))}

# 답변 초안 재생성 api
@app.post("/api/cs-auto/tickets/{ticket_id}/draft/regenerate")
def api_regenerate_answer_draft(ticket_id: int, payload: DraftRegenerateRequest) -> dict[str, object]:
    pass

# 답변 초안 승인 api
@app.post("/api/cs-auto/tickets/{ticket_id}/draft/approve")
def api_approve_answer_draft(ticket_id: int, payload: DraftApproveRequest) -> dict[str, object]:
    pass

# ---------------------------------------------------------------------------
# 
# ---------------------------------------------------------------------------



def _format_frontend_display_date(value: object) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%m-%d %H:%M")
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return parsed.strftime("%m-%d %H:%M")


def build_frontend_ticket_payload(row: dict[str, object] | None) -> dict[str, object] | None:
    if not row:
        return None

    risk_level = str(row.get("risk_level") or "LOW").upper()
    raw_status = str(row.get("status") or "")
    source_type = str(row.get("source_type") or "")
    has_draft = bool(row.get("draft_id"))
    has_response = bool(row.get("response_id"))
    is_chatbot_pending = source_type == "chatbot" and raw_status == "pending"
    status = "done" if has_response else "pending" if has_draft or is_chatbot_pending else "waiting_draft"
    priority_tone = "done" if has_response else "urgent" if risk_level == "HIGH" else "pending" if has_draft or is_chatbot_pending else "none"
    priority_label = "종료" if has_response else "긴급" if risk_level == "HIGH" else "대기"

    return {
        "id": f"TK-{row.get('ticket_id')}",
        "ticketId": row.get("ticket_id"),
        "draftId": row.get("draft_id") or None,
        "responseId": row.get("response_id") or None,
        "priorityLabel": priority_label,
        "priorityTone": priority_tone,
        "level": risk_level,
        "channel": source_type or "-",
        "channelIcon": "brand-blogger" if source_type == "naver_cafe" else "robot" if source_type == "chatbot" else "mail",
        "category": row.get("category") or "미분류",
        "status": status,
        "title": row.get("title") or "제목 없음",
        "assignee": row.get("assignee_display_name") or row.get("assignee_login_id") or "미할당",
        "assigneeAdminId": row.get("assignee_admin_id") or None,
        "statusText": "종료 처리되었습니다." if has_response else "답변 초안 검토 대기" if has_draft else "챗봇 상담원 확인 대기" if is_chatbot_pending else "답변 초안 생성 대기",
        "timeAgo": "-",
        "nickname": row.get("nickname") or "-",
        "userEmail": row.get("email") or "-",
        "email": row.get("email") or "-",
        "accountId": row.get("account_id") or "-",
        "createdAt": _format_frontend_display_date(row.get("inquiry_created_at")),
        "body": row.get("raw_query") or "",
        "aiSummary": row.get("summary") or "",
        "route": row.get("routing_target") or "-",
        "direction": row.get("routing_target") or "-",
        "risk": risk_level,
        "draft": row.get("draft_text") or row.get("final_text") or "",
        "draftStatus": "approved" if has_response else "draft" if has_draft else "none",
        "isDraftEditing": False,
        "regenCount": row.get("retry_count") or 0,
        "regenLimit": 3,
        "lastGeneratedAt": _format_frontend_display_date(row.get("draft_created_at")),
        "rawStatus": raw_status,
        "sourceType": source_type,
    }


def get_cs_auto_api_contract() -> dict[str, object]:
    return {
        "regeneration_flow": "request_draft_regeneration -> regenerate_agent(ticket_id, regeneration_reason)",
        "regeneration_agent_function": "agents.answer_agent.regenerate_agent",
        "draft_update_policy": "overwrite_answer_draft_text",
        "approval_policy": "insert_final_response_then_resolve_ticket",
        "detail_payload_sections": ["ticket", "evidence", "safety", "history", "operationLogs"],
        "draft_update_side_effects": [
            "answer_draft.draft_text overwrite",
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
