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

from chatbot.constants import CATEGORY, ROUTING_TARGET
from chatbot.schemas import ChatbotState
from config import settings

_TOXIC_KEYWORDS = ["욕설", "협박", "성희롱", "자살", "폭력"]

_SYSTEM_PROMPT = f"""당신은 게임 CS 챗봇의 오케스트레이터입니다.
사용자 문의를 아래 카테고리 중 하나로 분류하고 라우팅 대상을 결정하세요.

카테고리: {CATEGORY}
라우팅 대상: {ROUTING_TARGET}

규칙:
- '결제' 카테고리 → routing_target = "urgent_alert"
- 나머지 카테고리 → routing_target = "rag_reply"

반드시 아래 JSON 형식으로만 응답하세요:
{{"category": "<카테고리>", "routing_target": "<라우팅 대상>"}}"""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


def _toxic_filter(text: str) -> bool:
    return any(kw in text for kw in _TOXIC_KEYWORDS)


def orchestrator_node(state: ChatbotState) -> dict:
    user_message = state.get("user_message", "")

    if _toxic_filter(user_message):
        return {"category": "VOC", "routing_target": "urgent_alert"}

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ])

    try:
        parsed = json.loads(response.content)
        category = parsed.get("category", "FAQ")
        routing_target = parsed.get("routing_target", "rag_reply")
    except (json.JSONDecodeError, AttributeError):
        category = "FAQ"
        routing_target = "rag_reply"

    return {"category": category, "routing_target": routing_target}
