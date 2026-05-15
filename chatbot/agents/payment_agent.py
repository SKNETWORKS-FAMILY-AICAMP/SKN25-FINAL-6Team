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
from chatbot.tools.db_tools import (
    read_item_delivery_logs,
    read_payments,
    read_refunds,
    write_answer_draft,
    write_evidence_docs,
    write_ticket_analysis,
)
from config import settings

_SYSTEM_PROMPT = """당신은 게임 CS 결제 전문 Agent입니다.
결제 내역, 환불 기록, 아이템 지급 로그를 바탕으로 정확하고 공감적인 답변을 작성하세요.
근거가 되는 데이터를 명시하고, 해결 방법 또는 다음 단계를 안내하세요."""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
    )


def payment_agent_node(state: ChatbotState) -> dict:
    ticket_id = state["ticket_id"]
    account_id = state.get("account_id") or 0
    user_message = state.get("user_message", "")

    payments = read_payments.invoke({"account_id": account_id})
    delivery_logs = read_item_delivery_logs.invoke({"account_id": account_id})

    payment_ids = [p["payment_id"] for p in json.loads(payments)]
    refunds = read_refunds.invoke({"payment_id": payment_ids[0]}) if payment_ids else "[]"

    context = (
        f"결제 내역:\n{payments}\n\n"
        f"아이템 지급 로그:\n{delivery_logs}\n\n"
        f"환불 기록:\n{refunds}"
    )

    write_ticket_analysis.invoke({
        "payload": {"ticket_id": ticket_id, "category": "결제", "risk_level": "HIGH"},
    })

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"문의:\n{user_message}\n\n데이터:\n{context}"),
    ])

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": response.content},
    })
    draft_id = json.loads(draft_result).get("draft_id")

    write_evidence_docs.invoke({
        "payload": {"draft_id": draft_id, "source": "결제/지급 로그"},
    })

    return {"answer_draft": response.content, "draft_id": draft_id, "retry_count": 0}
