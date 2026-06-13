from __future__ import annotations

from chatbot.generation.response.fixed_responses import (
    BLOCK_RESPONSE,
    REVIEW_REQUIRED_RESPONSE,
    fallback_response_for_category,
)
from chatbot.notifications.github_issue import dispatch_github_issue_notification
from chatbot.observability.logger import EVENT_FINAL_RESPONSE_CREATED, log_event
from chatbot.repository.failed_query_repository import save_failed_query
from chatbot.repository.ticket_repository import update_qa_ticket_raw_query
from chatbot.schemas import ChatbotState


def _ticket_status_for_decision(decision: str, review_required: bool | None = None) -> str:
    # 운영자 검토가 필요한 문의는 pending으로 남기고, 자동 처리된 문의는 resolved로 닫는다.
    if decision == "REVIEW_REQUIRED" or review_required is True:
        return "pending"
    return "resolved"


def _is_faq_state(state: ChatbotState) -> bool:
    return (
        str(state.get("category") or "").strip().lower() == "faq"
        or state.get("reasoning_node") == "faq_agent"
        or state.get("should_use_rag") is True
    )


def _record_faq_safe_fallback_query(state: ChatbotState, decision: str) -> dict | None:
    # FAQ/RAG가 safety 단계에서 fallback된 경우 문서 보강 후보로 남긴다.
    if decision != "SAFE_FALLBACK" or not _is_faq_state(state):
        return None
    if state.get("faq_failure_reason"):
        return None
    ticket_id = state.get("ticket_id")
    if ticket_id is None:
        return None

    query = state.get("retrieval_query") or state.get("normalized_query") or state.get("raw_query") or ""
    return save_failed_query(
        {
            "ticket_id": ticket_id,
            "query": str(query),
            "category": state.get("category") or "faq",
            "reason": "safety_safe_fallback",
        }
    )


def final_response_node(state: ChatbotState) -> dict:
    # 1단계: safety_action에 따라 사용자에게 보여줄 최종 문구를 확정한다.
    decision = state["safety_action"]
    draft_text = state["draft_text"]

    if decision == "BLOCK_RESPONSE":
        final_text = BLOCK_RESPONSE
    elif decision in ("SAFE_FALLBACK", "MASKING"):
        final_text = fallback_response_for_category(state.get("category"))
    elif decision == "REVIEW_REQUIRED":
        final_text = draft_text or REVIEW_REQUIRED_RESPONSE
    else:
        final_text = draft_text

    # 2단계: 검토가 필요한 버그성 문의면 GitHub issue를 만들고, 아니면 skipped 결과만 남긴다.
    notification_result = dispatch_github_issue_notification({**state, "final_text": final_text})
    failed_query_result = _record_faq_safe_fallback_query(state, decision)

    # 3단계: 문의 내역 화면에서 볼 수 있도록 User/AI 최종 대화를 qa_ticket에 반영한다.
    raw_query = state.get("raw_query") or ""
    ticket_status_result = update_qa_ticket_raw_query(
        {
            "ticket_id": state["ticket_id"],
            "raw_query": f"User: {raw_query}\nAI: {final_text}",
            "safety_action": decision,
            "status": _ticket_status_for_decision(decision, state.get("review_required")),
        }
    )

    # 4단계: LangSmith/admin log에서 최종 처리 결과를 추적할 수 있게 이벤트를 남긴다.
    log_event(
        EVENT_FINAL_RESPONSE_CREATED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="final_response",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        status="ok",
        metadata={
            "safety_action": decision,
            "notification_status": notification_result.get("status"),
            "failed_query_result": failed_query_result,
            "ticket_status_result": ticket_status_result,
        },
    )

    return {
        "final_text": final_text,
        "notification_result": notification_result,
        "failed_query_result": failed_query_result,
        "ticket_status_result": ticket_status_result,
    }
