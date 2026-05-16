from __future__ import annotations

import json

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs


def voc_agent_node(state: ChatbotState) -> dict:
    ticket_id = state.get("ticket_id") or 0
    answer = "소중한 의견 감사합니다. 전달해 주신 내용은 운영 개선을 위해 접수하겠습니다."

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": answer},
    })
    draft_id = json.loads(draft_result).get("draft_id")
    write_evidence_docs.invoke({
        "payload": {"draft_id": draft_id, "source": "VOC 접수"},
    })

    return {
        "answer_draft": answer,
        "draft_id": draft_id,
        "retry_count": state.get("retry_count", 0),
    }
