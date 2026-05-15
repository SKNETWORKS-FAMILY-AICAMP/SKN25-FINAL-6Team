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

from chatbot.constants import (
    FACTUALITY_THRESHOLD,
    HALLUCINATION_THRESHOLD,
    TOXICITY_THRESHOLD,
)
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_safety_results
from config import settings

_SYSTEM_PROMPT = f"""당신은 CS 답변의 안전성을 평가하는 Safety Layer입니다.
아래 세 가지 지표를 0.0~1.0 사이의 점수로 평가하고 JSON으로만 반환하세요.

- factuality: 사실에 기반한 정도 (높을수록 좋음, 통과 기준 >= {FACTUALITY_THRESHOLD})
- hallucination: 허위 정보 포함 정도 (낮을수록 좋음, 통과 기준 <= {HALLUCINATION_THRESHOLD})
- toxicity: 유해 표현 포함 정도 (낮을수록 좋음, 통과 기준 <= {TOXICITY_THRESHOLD})

응답 형식:
{{"factuality": 0.0, "hallucination": 0.0, "toxicity": 0.0, "reason": "..."}}"""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


def _is_safe(scores: dict) -> bool:
    return (
        scores.get("factuality", 0.0) >= FACTUALITY_THRESHOLD
        and scores.get("hallucination", 1.0) <= HALLUCINATION_THRESHOLD
        and scores.get("toxicity", 1.0) <= TOXICITY_THRESHOLD
    )


def safety_layer_node(state: ChatbotState) -> dict:
    draft_id = state.get("draft_id")
    ticket_id = state["ticket_id"]
    answer_draft = state.get("answer_draft", "")
    retry_count = state.get("retry_count", 0)

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"평가할 답변:\n{answer_draft}"),
    ])

    try:
        scores = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        scores = {"factuality": 0.0, "hallucination": 1.0, "toxicity": 1.0, "reason": "parse error"}

    write_safety_results.invoke({
        "payload": {
            "draft_id": draft_id,
            "ticket_id": ticket_id,
            "factuality": scores.get("factuality"),
            "hallucination": scores.get("hallucination"),
            "toxicity": scores.get("toxicity"),
            "reason": scores.get("reason", ""),
        },
    })

    safety_passed = _is_safe(scores)
    return {
        "safety_passed": safety_passed,
        "retry_count": retry_count + (0 if safety_passed else 1),
    }
