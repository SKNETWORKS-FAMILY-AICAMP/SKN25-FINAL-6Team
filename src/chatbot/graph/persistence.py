from __future__ import annotations

import json

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs


def draft_persistence_node(state: ChatbotState) -> dict:
    """Persist the generated answer draft and its baseline evidence record."""
    draft_result = write_answer_draft.invoke({
        "payload": {
            "ticket_id": state["ticket_id"],
            "content": state["answer_draft"],
        },
    })
    draft_id = json.loads(draft_result)["draft_id"]

    write_evidence_docs.invoke({
        "payload": {
            "draft_id": draft_id,
            "source": f"{state['reasoning_node']}_create_agent",
        },
    })

    return {"draft_id": draft_id}
