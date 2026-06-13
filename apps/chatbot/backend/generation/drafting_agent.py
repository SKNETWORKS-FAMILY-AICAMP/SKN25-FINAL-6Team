from __future__ import annotations

from typing import Any

from chatbot.schemas import ChatbotState


# agent 응답 message에서 실제 텍스트 content만 추출한다.
def _message_text(message: Any) -> str:
    content = message["content"] if isinstance(message, dict) else message.content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


# concrete agent 실행 결과를 workflow가 저장할 draft_text state로 변환한다.
def build_draft_update(
    state: ChatbotState,
    result: dict[str, Any],
    node_name: str,
) -> dict[str, Any]:
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
