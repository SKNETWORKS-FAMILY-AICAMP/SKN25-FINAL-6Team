from __future__ import annotations

from typing import Any

from chatbot.schemas import ChatbotState


def _message_text(message: Any) -> str:
    content = message["content"] if isinstance(message, dict) else message.content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def build_draft_update(
    state: ChatbotState,
    result: dict[str, Any],
    node_name: str,
) -> dict[str, Any]:
    """Convert a concrete agent result into a StateGraph update."""
    messages = result["messages"]
    draft_text = _message_text(messages[-1])

    return {
        "messages": messages,
        "draft_text": draft_text,
        "retry_count": state["retry_count"],
        "category": state["category"],
        "routing_target": state["routing_target"],
        "reasoning_node": node_name,
    }
