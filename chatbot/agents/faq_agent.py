from __future__ import annotations

import hashlib
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
from chatbot.tools.cache_tools import get_cache, set_cache
from chatbot.tools.db_tools import (
    write_answer_draft,
    write_evidence_docs,
    write_ticket_analysis,
)
from chatbot.tools.vector_tools import embed_query, rerank_documents, search_documents
from config import settings

_SYSTEM_PROMPT = """당신은 게임 CS FAQ 전문 Agent입니다.
검색된 문서를 근거로 정확하고 간결한 답변을 작성하세요.
답변의 출처 문서 제목을 반드시 포함하세요."""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
    )


def faq_agent_node(state: ChatbotState) -> dict:
    ticket_id = state["ticket_id"]
    user_message = state.get("user_message", "")

    query_hash = hashlib.sha256(user_message.encode()).hexdigest()
    cache_result = json.loads(get_cache.invoke({"query_hash": query_hash}))
    if cache_result.get("hit"):
        draft_result = write_answer_draft.invoke({
            "payload": {"ticket_id": ticket_id, "content": cache_result["answer"]},
        })
        draft_id = json.loads(draft_result).get("draft_id")
        return {"answer_draft": cache_result["answer"], "draft_id": draft_id, "retry_count": 0}

    embedding = embed_query.invoke({"text": user_message})
    docs_json = search_documents.invoke({"embedding_json": embedding})
    reranked = rerank_documents.invoke({"docs_json": docs_json, "query": user_message})

    write_ticket_analysis.invoke({
        "payload": {"ticket_id": ticket_id, "category": "FAQ", "risk_level": "LOW"},
    })

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"문의:\n{user_message}\n\n검색된 문서:\n{reranked}"),
    ])

    set_cache.invoke({"query_hash": query_hash, "answer": response.content})

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": response.content},
    })
    draft_id = json.loads(draft_result).get("draft_id")

    write_evidence_docs.invoke({
        "payload": {"draft_id": draft_id, "source": "FAQ 문서"},
    })

    return {"answer_draft": response.content, "draft_id": draft_id, "retry_count": 0}
