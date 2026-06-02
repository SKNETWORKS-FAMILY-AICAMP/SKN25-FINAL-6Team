from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel

from chatbot.constants import VOC_FIXED_RESPONSE
from chatbot.schemas import ChatbotState


VocType = Literal["suggestion", "complaint", "praise", "multi_intent", "other"]
VocSentiment = Literal["positive", "neutral", "negative"]


class VocClassification(BaseModel):
    voc_type: VocType
    sentiment: VocSentiment
    topic_keywords: list[str]


def _active_text(state: ChatbotState) -> str:
    return str(state.get("enriched_query") or state.get("raw_query") or "").strip()


def _classify_voc_with_llm(text: str) -> VocClassification:
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not api_key or not model:
        raise RuntimeError("OpenAI settings are missing.")

    from langchain_openai import ChatOpenAI

    classifier = ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0,
    ).with_structured_output(VocClassification)

    return classifier.invoke([
        (
            "system",
            "You classify Korean game customer feedback into VOC fields. "
            "Return only the requested structured output. "
            "voc_type must be one of suggestion, complaint, praise, multi_intent, other. "
            "sentiment must be one of positive, neutral, negative. "
            "topic_keywords must contain 2 to 5 normalized Korean noun keywords. "
            "Do not return a summary.",
        ),
        (
            "user",
            "Classify this VOC.\n"
            f"content: {text}",
        ),
    ])


def _classify_voc(text: str) -> tuple[str, str, list[str]]:
    result = _classify_voc_with_llm(text)
    return result.voc_type, result.sentiment, result.topic_keywords


def _build_voc_response(voc_type: str) -> str:
    responses = {
        "complaint": (
            "소중한 의견을 남겨주셔서 감사합니다.\n"
            "말씀해주신 불편 사항은 담당 부서에서 확인할 수 있도록 접수하겠습니다."
        ),
        "suggestion": (
            "좋은 제안 남겨주셔서 감사합니다.\n"
            "보내주신 개선 의견은 서비스 운영 및 업데이트 검토에 참고할 수 있도록 전달하겠습니다."
        ),
        "praise": (
            "따뜻한 의견 남겨주셔서 감사합니다.\n"
            "보내주신 응원은 서비스 운영팀에 전달하겠습니다. 앞으로도 좋은 경험을 드릴 수 있도록 노력하겠습니다."
        ),
        "multi_intent": (
            "여러 의견을 함께 남겨주셔서 감사합니다.\n"
            "말씀해주신 내용은 항목별로 확인할 수 있도록 접수하겠습니다."
        ),
        "other": (
            "의견 남겨주셔서 감사합니다.\n"
            "보내주신 내용은 담당 부서에서 참고할 수 있도록 접수하겠습니다."
        ),
    }
    return responses.get(voc_type, responses["other"])


def voc_agent_node(state: ChatbotState) -> dict:
    raw_content = _active_text(state)
    if state.get("is_actionable") is False and state.get("should_use_rag") is False:
        voc_type, sentiment, topic_keywords = "other", "negative", []
        answer = VOC_FIXED_RESPONSE
        safety_reason = str(state.get("fallback_reason") or "non_actionable_voc_fallback")
    else:
        voc_type, sentiment, topic_keywords = _classify_voc(raw_content)
        answer = _build_voc_response(voc_type)
        safety_reason = "VOC template response skips LLM safety validation."

    return {
        "draft_text": answer,
        "draft_id": state.get("draft_id"),
        "retry_count": state["retry_count"],
        "category": state.get("category") or "voc",
        "routing_target": state["routing_target"],
        "reasoning_node": "voc_agent",
        "safety_passed": True,
        "safety_action": "AUTO_RESPONSE",
        "safety_reason": safety_reason,
        "voc_type": voc_type,
        "sentiment": sentiment,
        "topic_keywords": topic_keywords,
    }
