from __future__ import annotations

import json
from typing import Any

from chatbot.agent import invoke_chatbot_agent
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs


def _message_text(message: Any) -> str:
    content = message["content"] if isinstance(message, dict) else message.content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def drafting_agent_node(state: ChatbotState, node_name: str) -> dict[str, Any]:
    """Run the shared create_agent drafting unit inside a LangGraph category node."""
    result = invoke_chatbot_agent(state)
    messages = result["messages"]
    answer_draft = _message_text(messages[-1])
    ticket_id = state["ticket_id"]
    draft_id = None
    if "draft_id" in result and result["draft_id"] is not None:
        draft_id = result["draft_id"]
    elif "draft_id" in state and state["draft_id"] is not None:
        draft_id = state["draft_id"]

    if draft_id is None:
        draft_result = write_answer_draft.invoke({
            "payload": {"ticket_id": ticket_id, "content": answer_draft},
        })
        draft_id = json.loads(draft_result)["draft_id"]
        write_evidence_docs.invoke({
            "payload": {"draft_id": draft_id, "source": f"{node_name}_create_agent"},
        })

    return {
        "messages": messages,
        "answer_draft": answer_draft,
        "draft_id": draft_id,
        "retry_count": state["retry_count"],
        "category": state["category"],
        "routing_target": state["routing_target"],
        "reasoning_node": node_name,
    }
