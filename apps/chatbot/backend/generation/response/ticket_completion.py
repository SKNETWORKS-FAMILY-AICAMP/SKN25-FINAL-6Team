from __future__ import annotations

from generation.response.fixed_responses import (
    BLOCK_RESPONSE,
    REVIEW_REQUIRED_RESPONSE,
    fallback_response_for_category,
)
from notifications.github_issue import dispatch_github_issue_notification
from observability.langfuse import link_chatbot_trace
from observability.logger import EVENT_TICKET_COMPLETION_COMPLETED, log_event
from repository.failed_query_repository import save_failed_query
from repository.ticket_repository import delete_qa_ticket, update_qa_ticket_raw_query, update_session_qa_tickets_status
from schemas import ChatbotState
from common.observability.langfuse import observe_if_enabled


def _ticket_status_for_decision(decision: str, review_required: bool | None = None) -> str:
    # 운영자 검토가 필요한 문의는 pending으로 남기고, 자동 처리된 문의는 resolved로 닫는다.
    if decision == "REVIEW_REQUIRED" or review_required is True:
        return "pending"
    return "resolved"


def _ticket_status_for_state(state: ChatbotState, decision: str) -> str:
    return _ticket_status_for_decision(decision, state.get("review_required"))


def _normalized_bug_text(text: str) -> str:
    return "\n".join(line.strip() for line in str(text or "").splitlines() if line.strip())


def _join_unique_bug_parts(parts: list[str]) -> str:
    normalized_seen: set[str] = set()
    unique_parts: list[str] = []
    for part in parts:
        clean_part = str(part or "").strip()
        normalized = _normalized_bug_text(clean_part)
        if not normalized or normalized in normalized_seen:
            continue
        normalized_seen.add(normalized)
        unique_parts.append(clean_part)
    return "\n\n".join(unique_parts)


def _format_bug_collection_user_text(state: ChatbotState) -> str | None:
    if not state.get("bug_report_form"):
        return None

    initial_query = str(state.get("initial_bug_query") or state.get("raw_query") or "").strip()
    reproduction_info = str(state.get("bug_report_form") or state.get("raw_query") or "").strip()
    return _join_unique_bug_parts([initial_query, reproduction_info])


def _format_bug_review_session_text(state: ChatbotState) -> str | None:
    if not state.get("bug_report_form"):
        return None

    parts: list[str] = []
    previous_lines: list[str] = []
    for message in state.get("previous_messages") or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "").strip()
        if not role or not content:
            continue
        label = "User" if role == "user" else "AI" if role == "assistant" else role
        previous_lines.append(f"{label}: {content}")

    if previous_lines:
        parts.append("[이전 대화]\n" + "\n".join(previous_lines))

    reproduction_info = str(state.get("bug_report_form") or state.get("raw_query") or "").strip()
    initial_query = "" if previous_lines else str(state.get("initial_bug_query") or "").strip()
    if initial_query and _normalized_bug_text(initial_query) != _normalized_bug_text(reproduction_info):
        parts.append("[초기 문의]\n" + initial_query)

    if reproduction_info:
        parts.append("[재현 정보]\n" + reproduction_info)

    return _join_unique_bug_parts(parts)


def _update_bug_review_session_status(state: ChatbotState) -> dict | None:
    if not state.get("bug_report_form"):
        return None
    if state.get("review_required") is not True and state.get("safety_action") != "REVIEW_REQUIRED":
        return None
    return update_session_qa_tickets_status(
        {
            "session_id": state.get("session_id"),
            "user_id": state.get("user_id"),
            "account_id": state.get("account_id"),
            "status": "pending",
        }
    )


def _is_category_redirect_response(final_text: str) -> bool:
    text = " ".join(str(final_text or "").split())
    if not text:
        return False

    redirect_markers = (
        "다른 카테고리",
        "올바른 카테고리",
        "알맞은 카테고리",
        "카테고리를 선택",
        "카테고리에 문의",
        "카테고리로 문의",
        "이 채널은",
        "채널은",
        "문의 전용",
        "전용입니다",
    )
    inquiry_markers = ("문의", "질문", "카테고리", "채널")
    return any(marker in text for marker in redirect_markers) and any(marker in text for marker in inquiry_markers)


def _is_faq_state(state: ChatbotState) -> bool:
    routing_target = str(state.get("routing_target") or "").strip().lower()
    return (
        str(state.get("category") or "").strip().lower() == "faq"
        or state.get("reasoning_node") == "faq_agent"
        or routing_target in {"faq_agent", "rag_reply"}
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


def ticket_completion_node(state: ChatbotState) -> dict:
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
    if _is_category_redirect_response(final_text):
        delete_result = delete_qa_ticket({"ticket_id": state["ticket_id"]})
        log_event(
            EVENT_TICKET_COMPLETION_COMPLETED,
            ticket_id=state.get("ticket_id"),
            session_id=state.get("session_id"),
            node_name="ticket_completion",
            category=state.get("category"),
            routing_target=state.get("routing_target"),
            status="skipped",
            metadata={
                "skip_reason": "category_redirect_response",
                "delete_result": delete_result,
            },
        )
        return {
            "final_text": final_text,
            "notification_result": {"status": "skipped", "reason": "category redirect response"},
            "failed_query_result": None,
            "ticket_status_result": delete_result,
        }

    raw_query = state.get("raw_query") or ""
    formatted_session_text = _format_bug_review_session_text(state)
    formatted_user_text = formatted_session_text or _format_bug_collection_user_text(state)
    github_issue_content = formatted_user_text or raw_query
    formatted_raw_query = f"User: {formatted_user_text or raw_query}\nAI: {final_text}"
    notification_result = dispatch_github_issue_notification(
        {
            **state,
            "final_text": final_text,
            "github_issue_content": github_issue_content,
        }
    )
    failed_query_result = _record_faq_safe_fallback_query(state, decision)

    # 3단계: 문의 내역 화면에서 볼 수 있도록 User/AI 최종 대화를 qa_ticket에 반영한다.
    ticket_status_result = update_qa_ticket_raw_query(
        {
            "ticket_id": state["ticket_id"],
            "raw_query": formatted_raw_query or f"User: {raw_query}\nAI: {final_text}",
            "status": _ticket_status_for_state(state, decision),
        }
    )
    session_status_result = _update_bug_review_session_status(state)

    # 5단계: Langfuse/admin log에서 최종 처리 결과를 추적할 수 있게 이벤트를 남긴다.
    log_event(
        EVENT_TICKET_COMPLETION_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="ticket_completion",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        status="ok",
        metadata={
            "safety_action": decision,
            "notification_status": notification_result.get("status"),
            "failed_query_result": failed_query_result,
            "ticket_status_result": ticket_status_result,
            "session_status_result": session_status_result,
        },
    )

    return {
        "final_text": final_text,
        "notification_result": notification_result,
        "failed_query_result": failed_query_result,
        "ticket_status_result": ticket_status_result,
        "session_status_result": session_status_result,
    }


_original_ticket_completion_node = ticket_completion_node


@observe_if_enabled(
    name="ticket_completion",
    as_type="chain",
    tags=["chatbot", "feature:completion"],
)
def ticket_completion_node(state: ChatbotState) -> dict:
    link_chatbot_trace(
        state,
        tags=["feature:completion"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "safety_action": state.get("safety_action"),
            "review_required": state.get("review_required"),
            "draft_text_length": len(state.get("draft_text") or ""),
        },
    )
    result = _original_ticket_completion_node(state)
    link_chatbot_trace(
        state,
        tags=["feature:completion"],
        metadata_source={**state, **result},
        output_payload=result,
    )
    return result
