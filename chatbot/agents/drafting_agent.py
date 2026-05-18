from __future__ import annotations

import json
from typing import Any

from chatbot.agent import invoke_chatbot_agent
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs


def _message_text(message: Any) -> str:
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def _last_message_text(result: dict[str, Any]) -> str:
    messages = result.get("messages", [])
    if not messages:
        return ""
    return _message_text(messages[-1])


def drafting_agent_node(state: ChatbotState, node_name: str) -> dict[str, Any]:
    """Run the shared create_agent drafting unit inside a LangGraph category node."""
    result = invoke_chatbot_agent(state)
    answer_draft = result.get("answer_draft") or result.get("final_answer") or _last_message_text(result)
    if not answer_draft:
        answer_draft = "문의 내용을 확인했습니다. 추가 확인이 필요한 경우 담당자가 검토한 뒤 안내드리겠습니다."
    ticket_id = state.get("ticket_id") or 0
    draft_id = result.get("draft_id") or state.get("draft_id")

    if draft_id is None:
        draft_result = write_answer_draft.invoke({
            "payload": {"ticket_id": ticket_id, "content": answer_draft},
        })
        draft_id = json.loads(draft_result).get("draft_id")
        write_evidence_docs.invoke({
            "payload": {"draft_id": draft_id, "source": f"{node_name}_create_agent"},
        })

    return {
        "messages": result.get("messages", state.get("messages", [])),
        "answer_draft": answer_draft,
        "draft_id": draft_id,
        "retry_count": state.get("retry_count", 0),
        "category": state.get("category"),
        "routing_target": state.get("routing_target"),
        "reasoning_node": node_name,
    }

