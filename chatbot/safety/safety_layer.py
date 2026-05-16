from __future__ import annotations

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_safety_results


def safety_layer_node(state: ChatbotState) -> dict:
    answer_draft = state.get("answer_draft") or ""
    draft_id = state.get("draft_id")
    ticket_id = state.get("ticket_id")
    is_blocked = any(keyword in answer_draft for keyword in ("욕설", "혐오", "폭력"))
    safety_passed = not is_blocked
    decision_type = "AUTO_RESPONSE" if safety_passed else "BLOCK_RESPONSE"

    write_safety_results.invoke({
        "payload": {
            "draft_id": draft_id,
            "ticket_id": ticket_id,
            "decision_type": decision_type,
            "factuality": 0.8 if safety_passed else 0.0,
            "hallucination": 0.2 if safety_passed else 1.0,
            "toxicity": 0.1 if safety_passed else 1.0,
            "reason": "baseline keyword safety check",
        },
    })

    return {
        "safety_passed": safety_passed,
        "safety_action": decision_type,
        "safety_reason": "baseline keyword safety check",
        "review_required": decision_type == "REVIEW_QUEUE",
        "retry_count": state.get("retry_count", 0) + (1 if is_blocked else 0),
    }
