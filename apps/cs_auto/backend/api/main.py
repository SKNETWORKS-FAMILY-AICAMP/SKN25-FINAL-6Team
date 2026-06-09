"""
CS Auto API route skeletons.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

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


class CafeCommentRequest(BaseModel):
    response_id: int
    admin_id: int


# ---------------------------------------------------------------------------
# Frontend read APIs
# ---------------------------------------------------------------------------
@app.get("/health")
@app.get("/api/cs-auto/health")
def api_health_check() -> dict[str, object]:
    return {"status": "ok"}


@app.get("/api/cs-auto/tickets")
def api_get_review_tickets(
    limit: int | None = None,
    status: str | None = None,
    assignee_admin_id: int | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    page: int | None = None,
) -> dict[str, object]:
    pass


@app.get("/api/cs-auto/tickets/{ticket_id}")
def api_get_ticket_detail(ticket_id: int) -> dict[str, object]:
    pass


# ---------------------------------------------------------------------------
# Batch APIs
# ---------------------------------------------------------------------------
@app.post("/internal/cs-auto/batch/refresh")
def api_refresh_cs_auto_batch() -> dict[str, object]:
    pass


# ---------------------------------------------------------------------------
# Operator event APIs
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


@app.patch("/api/cs-auto/tickets/{ticket_id}/draft")
def api_update_answer_draft(ticket_id: int, payload: DraftUpdateRequest) -> dict[str, object]:
    pass


@app.post("/api/cs-auto/tickets/{ticket_id}/draft/regenerate")
def api_regenerate_answer_draft(ticket_id: int, payload: DraftRegenerateRequest) -> dict[str, object]:
    pass


@app.post("/api/cs-auto/tickets/{ticket_id}/draft/approve")
def api_approve_answer_draft(ticket_id: int, payload: DraftApproveRequest) -> dict[str, object]:
    pass


@app.post("/api/cs-auto/tickets/{ticket_id}/cafe/comment")
def api_upload_cafe_comment(ticket_id: int, payload: CafeCommentRequest) -> dict[str, object]:
    pass
