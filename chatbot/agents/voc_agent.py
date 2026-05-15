from __future__ import annotations

import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs, write_ticket_analysis
from config import settings

_SYSTEM_PROMPT = """당신은 게임 CS VOC(고객 의견) 전문 Agent입니다.
고객의 불만, 제안, 칭찬 등 다양한 의견을 공감적으로 수용하고,
적절한 후속 조치나 피드백 접수 확인 메시지를 제공하세요."""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.5,
    )


def voc_agent_node(state: ChatbotState) -> dict:
    ticket_id = state["ticket_id"]
    user_message = state.get("user_message", "")

    write_ticket_analysis.invoke({
        "payload": {"ticket_id": ticket_id, "category": "VOC", "risk_level": "LOW"},
    })

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"고객 의견:\n{user_message}"),
    ])

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": response.content},
    })
    draft_id = json.loads(draft_result).get("draft_id")

    write_evidence_docs.invoke({
        "payload": {"draft_id": draft_id, "source": "VOC 처리"},
    })

    return {"answer_draft": response.content, "draft_id": draft_id, "retry_count": 0}
