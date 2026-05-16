from __future__ import annotations

import hashlib
import json

from chatbot.schemas import ChatbotState
from chatbot.tools.cache_tools import get_cache, set_cache
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs


def faq_agent_node(state: ChatbotState) -> dict:
    content = state.get("cleaned_content") or state.get("raw_content") or ""
    ticket_id = state.get("ticket_id") or 0
    query_hash = hashlib.sha256(content.encode()).hexdigest()
    cache_result = json.loads(get_cache.invoke({"query_hash": query_hash}))

    if cache_result.get("hit"):
        answer = cache_result["answer"]
        source = "faq_cache"
    else:
        answer = (
            "문의 내용을 FAQ 기준으로 확인했습니다. "
            "현재 확인 가능한 일반 안내를 바탕으로 답변 초안을 생성했습니다."
        )
        source = "faq_baseline"
        set_cache.invoke({"query_hash": query_hash, "answer": answer})

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": answer},
    })
    draft_id = json.loads(draft_result).get("draft_id")
    write_evidence_docs.invoke({
        "payload": {"draft_id": draft_id, "source": source},
    })

    return {
        "answer_draft": answer,
        "draft_id": draft_id,
        "retry_count": state.get("retry_count", 0),
    }
