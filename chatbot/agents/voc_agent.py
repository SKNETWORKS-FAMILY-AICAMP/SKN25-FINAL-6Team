from __future__ import annotations

import json

from chatbot.constants import VOC_FIXED_RESPONSE
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs, write_voc_feedback


def _active_text(state: ChatbotState) -> str:
    return state.get("cleaned_content") or state.get("raw_content") or ""


def _classify_voc(text: str) -> tuple[str, str, str]:
    if any(keyword in text for keyword in ("불만", "별로", "너무 적", "화나", "짜증")):
        return "complaint", "negative", "불만성 VOC"
    if any(keyword in text for keyword in ("건의", "제안", "추가", "개선", "바꿔")):
        return "suggestion", "neutral", "건의성 VOC"
    if any(keyword in text for keyword in ("칭찬", "좋아요", "재밌", "감사")):
        return "praise", "positive", "칭찬성 VOC"
    if "?" in text and any(keyword in text for keyword in ("불만", "건의", "제안", "칭찬")):
        return "multi_intent", "neutral", "다중 의도 VOC"
    return "other", "neutral", "기타 VOC"


def voc_agent_node(state: ChatbotState) -> dict:
    raw_content = _active_text(state)
    voc_type, sentiment, summary = _classify_voc(raw_content)
    ticket_id = state.get("ticket_id") or 0

    write_voc_feedback.invoke({
        "payload": {
            "ticket_id": ticket_id,
            "user_id": state.get("user_id"),
            "account_id": state.get("account_id"),
            "voc_type": voc_type,
            "sentiment": sentiment,
            "raw_content": raw_content,
            "summary": summary,
        },
    })

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": VOC_FIXED_RESPONSE},
    })
    draft_id = json.loads(draft_result).get("draft_id")

    write_evidence_docs.invoke({
        "payload": {"draft_id": draft_id, "source": "VOC fixed response"},
    })

    return {
        "answer_draft": VOC_FIXED_RESPONSE,
        "draft_id": draft_id,
        "retry_count": state.get("retry_count", 0),
        "category": "VOC",
        "routing_target": state.get("routing_target", "rag_reply"),
        "reasoning_node": "voc_agent",
        "safety_passed": True,
        "safety_action": "AUTO_RESPONSE",
        "safety_reason": "VOC fixed response skips LLM safety validation.",
        "voc_type": voc_type,
        "voc_sentiment": sentiment,
        "voc_summary": summary,
    }
