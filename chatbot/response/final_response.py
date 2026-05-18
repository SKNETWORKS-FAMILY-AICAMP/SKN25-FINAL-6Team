from __future__ import annotations

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import append_qa_ticket_message


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
    answer_draft = state["answer_draft"]

    if decision == "BLOCK_RESPONSE":
        final_answer = _block_answer()
    elif decision in ("SAFE_FALLBACK", "MASKING"):
        final_answer = _fallback_answer()
    elif decision == "REVIEW_QUEUE":
        final_answer = _review_answer()
    else:
        final_answer = answer_draft

    append_qa_ticket_message.invoke({
        "payload": {
            "ticket_id": state["ticket_id"],
            "role": "assistant",
            "content": final_answer,
        },
    })

    return {
        "final_answer": final_answer,
    }
