from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs, write_voc_feedback
from config import settings


VocType = Literal["suggestion", "complaint", "praise", "multi_intent", "other"]
VocSentiment = Literal["positive", "neutral", "negative"]


class VocClassification(BaseModel):
    voc_type: VocType
    sentiment: VocSentiment
    summary: str


def _active_text(state: ChatbotState) -> str:
    return state["cleaned_content"]


def _classify_voc_with_llm(text: str) -> VocClassification:
    if not settings.openai_api_key or not settings.openai_model:
        raise RuntimeError("OpenAI settings are missing.")

    from langchain_openai import ChatOpenAI

    classifier = ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
    ).with_structured_output(VocClassification)

    return classifier.invoke([
        (
            "system",
            "You classify Korean game customer feedback into VOC fields. "
            "Return only the requested structured output. "
            "voc_type must be one of suggestion, complaint, praise, multi_intent, other. "
            "sentiment must be one of positive, neutral, negative. "
            "summary must be a concise Korean phrase.",
        ),
        (
            "user",
            "Classify this VOC.\n"
            f"content: {text}",
        ),
    ])


def _classify_voc(text: str) -> tuple[str, str, str]:
    result = _classify_voc_with_llm(text)
    return result.voc_type, result.sentiment, result.summary


def _build_voc_response(voc_type: str) -> str:
    responses = {
        "complaint": (
            "소중한 의견 남겨주셔서 감사합니다.\n"
            "이용 중 불편을 느끼신 부분은 관련 부서에서 확인할 수 있도록 접수하겠습니다. "
            "추가 확인이 필요한 경우 상담원이 이어서 안내드릴 수 있습니다."
        ),
        "suggestion": (
            "좋은 제안 남겨주셔서 감사합니다.\n"
            "말씀해주신 개선 의견은 서비스 운영 및 업데이트 검토 시 참고할 수 있도록 전달하겠습니다."
        ),
        "praise": (
            "따뜻한 의견 남겨주셔서 감사합니다.\n"
            "보내주신 응원은 서비스 운영팀에 잘 전달하겠습니다. 앞으로도 더 좋은 경험을 드릴 수 있도록 노력하겠습니다."
        ),
        "multi_intent": (
            "여러 의견을 함께 남겨주셔서 감사합니다.\n"
            "말씀해주신 내용은 항목별로 확인할 수 있도록 접수하겠습니다. 확인이 필요한 부분은 상담원이 이어서 안내드릴 수 있습니다."
        ),
        "other": (
            "의견 남겨주셔서 감사합니다.\n"
            "보내주신 내용은 담당 부서에서 참고할 수 있도록 접수하겠습니다."
        ),
    }
    return responses[voc_type]


def voc_agent_node(state: ChatbotState) -> dict:
    raw_content = _active_text(state)
    voc_type, sentiment, summary = _classify_voc(raw_content)
    ticket_id = state["ticket_id"]
    answer = _build_voc_response(voc_type)

    write_voc_feedback.invoke({
        "payload": {
            "ticket_id": ticket_id,
            "user_id": state["user_id"],
            "account_id": state["account_id"],
            "voc_type": voc_type,
            "sentiment": sentiment,
            "raw_content": raw_content,
            "summary": summary,
        },
    })

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": answer},
    })
    draft_id = json.loads(draft_result)["draft_id"]

    write_evidence_docs.invoke({
        "payload": {"draft_id": draft_id, "source": f"VOC template response: {voc_type}"},
    })

    return {
        "answer_draft": answer,
        "draft_id": draft_id,
        "retry_count": state["retry_count"],
        "category": "VOC",
        "routing_target": state["routing_target"],
        "reasoning_node": "voc_agent",
        "safety_passed": True,
        "safety_action": "AUTO_RESPONSE",
        "safety_reason": "VOC template response skips LLM safety validation.",
        "voc_type": voc_type,
        "voc_sentiment": sentiment,
        "voc_summary": summary,
    }
