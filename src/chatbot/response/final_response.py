from __future__ import annotations

import json

from chatbot.notifications.dispatcher import dispatch_urgent_alert
from chatbot.observability.logger import EVENT_FINAL_RESPONSE_CREATED, log_event
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_final_response


def _fallback_answer() -> str:
    return (
        "문의 내용을 바로 확인하기 어려워 일반 안내로 답변드립니다. "
        "담당자가 확인할 수 있도록 접수해 두겠습니다."
    )


def _block_answer() -> str:
    return "안전한 상담 진행을 위해 해당 답변은 제공할 수 없습니다."


def _review_answer() -> str:
    return (
        "문의하신 내용은 추가 확인이 필요한 사항으로 접수되었습니다. "
        "담당자가 검토한 뒤 안내드리겠습니다."
    )


def final_response_node(state: ChatbotState) -> dict:
    decision = state["safety_action"]
    draft_text = state["draft_text"]

    if decision == "BLOCK_RESPONSE":
        final_text = _block_answer()
    elif decision in ("SAFE_FALLBACK", "MASKING"):
        final_text = _fallback_answer()
    elif decision == "REVIEW_QUEUE":
        final_text = _review_answer()
    else:
        final_text = draft_text

    notification_result = dispatch_urgent_alert({**state, "final_text": final_text})

    final_response_result = json.loads(write_final_response.invoke({
        "payload": {
            "ticket_id": state["ticket_id"],
            "draft_id": state.get("draft_id"),
            "final_text": final_text,
            "safety_action": decision,
        },
    }))

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
        },
    )

    return {
        "final_text": final_text,
        "final_response_result": final_response_result,
        "notification_result": notification_result,
    }
