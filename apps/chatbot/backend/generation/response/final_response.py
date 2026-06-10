from __future__ import annotations

import json

from chatbot.generation.response.fixed_responses import (
    BLOCK_RESPONSE,
    REVIEW_QUEUE_RESPONSE,
    fallback_response_for_category,
)
from chatbot.notifications.dispatcher import dispatch_urgent_alert
from chatbot.observability.logger import EVENT_FINAL_RESPONSE_CREATED, log_event
from chatbot.repository.final_response_repository import save_final_response
from chatbot.repository.ticket_repository import update_qa_ticket_status as update_ticket_status
from chatbot.schemas import ChatbotState


write_final_response = save_final_response
update_qa_ticket_status = update_ticket_status


def _call_repository_or_tool(target, payload: dict) -> dict:
    if hasattr(target, "invoke"):
        result = target.invoke({"payload": payload})
        return json.loads(result) if isinstance(result, str) else result
    return target(payload)


def _ticket_status_for_decision(decision: str) -> str:
    # 안전성 결정에 따라 QA 티켓을 해결 완료 또는 검토 대기로 갱신한다.
    if decision == "REVIEW_QUEUE":
        return "pending"
    if decision == "BLOCK_RESPONSE":
        return "pending"
    return "resolved"


def final_response_node(state: ChatbotState) -> dict:
    # 1단계: safety_action에 따라 사용자에게 보여줄 최종 문구를 확정한다.
    decision = state["safety_action"]
    draft_text = state["draft_text"]

    if decision == "BLOCK_RESPONSE":
        final_text = BLOCK_RESPONSE
    elif decision in ("SAFE_FALLBACK", "MASKING"):
        final_text = fallback_response_for_category(state.get("category"))
    elif decision == "REVIEW_QUEUE":
        final_text = REVIEW_QUEUE_RESPONSE
    else:
        final_text = draft_text

    # 2단계: 긴급 알림 대상이면 외부 알림을 보내고, 아니면 skipped 상태로 남긴다.
    notification_result = dispatch_urgent_alert({**state, "final_text": final_text})

    # 3단계: final_response와 qa_ticket 상태를 DB에 저장한다.
    final_response_result = _call_repository_or_tool(
        write_final_response,
        {
            "ticket_id": state["ticket_id"],
            "draft_id": state.get("draft_id"),
            "final_text": final_text,
            "safety_action": decision,
        }
    )
    ticket_status_result = _call_repository_or_tool(
        update_qa_ticket_status,
        {
            "ticket_id": state["ticket_id"],
            "status": _ticket_status_for_decision(decision),
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
            "ticket_status_result": ticket_status_result,
        },
    )

    return {
        "final_text": final_text,
        "final_response_result": final_response_result,
        "notification_result": notification_result,
        "ticket_status_result": ticket_status_result,
    }
