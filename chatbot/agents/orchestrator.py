from __future__ import annotations

from chatbot.constants import CATEGORY, ROUTING_TARGET
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_qa_ticket, write_ticket_analysis


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def _classify(cleaned_content: str) -> tuple[str, str]:
    if any(keyword in cleaned_content for keyword in ("결제", "환불", "미지급", "아이템")):
        return "결제", "urgent_alert"
    if any(keyword in cleaned_content for keyword in ("버그", "오류", "튕김", "끼임")):
        return "인게임버그", "rag_reply"
    if any(keyword in cleaned_content for keyword in ("건의", "불만", "칭찬", "의견")):
        return "VOC", "rag_reply"
    return "FAQ", "rag_reply"


def _safe_category(category: str) -> str:
    return category if category in CATEGORY else "FAQ"


def _safe_routing_target(routing_target: str) -> str:
    return routing_target if routing_target in ROUTING_TARGET else "rag_reply"


def orchestrator_node(state: ChatbotState) -> dict:
    ticket_id = state.get("ticket_id") or 1001
    raw_content = state.get("raw_content") or ""
    cleaned_content = state.get("cleaned_content") or _normalize_text(raw_content)
    category, routing_target = _classify(cleaned_content)
    category = _safe_category(category)
    routing_target = _safe_routing_target(routing_target)

    write_qa_ticket.invoke({
        "payload": {
            "ticket_id": ticket_id,
            "user_id": state.get("user_id"),
            "account_id": state.get("account_id"),
            "raw_content": raw_content,
            "cleaned_content": cleaned_content,
            "source_type": state.get("source_type"),
        },
    })
    write_ticket_analysis.invoke({
        "payload": {
            "ticket_id": ticket_id,
            "category": category,
            "routing_target": routing_target,
        },
    })

    return {
        "ticket_id": ticket_id,
        "cleaned_content": cleaned_content,
        "category": category,
        "routing_target": routing_target,
    }
