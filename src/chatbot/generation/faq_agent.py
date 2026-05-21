from __future__ import annotations

import os

from chatbot.generation.policies import FAQ_POLICY
from chatbot.observability.logger import log_event
from chatbot.retrieval.vector_tools import embed_query, rerank_documents, search_documents
from chatbot.schemas import ChatbotState
from config import settings

EVENT_NODE_STARTED = "node_started"
EVENT_NODE_COMPLETED = "node_completed"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _generate_faq_answer(query: str, evidence_json: str) -> str:
    if not settings.openai_api_key or not settings.openai_model:
        raise RuntimeError("OpenAI settings are missing.")

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
        max_tokens=_env_int("FAQ_ANSWER_MAX_TOKENS", 450),
    )
    response = llm.invoke([
        (
            "system",
            "You are a concise Korean game customer-support FAQ assistant. "
            "Answer only from the provided evidence. "
            "If evidence is insufficient, say that an operator will check it.",
        ),
        (
            "user",
            "User question:\n"
            f"{query}\n\n"
            "FAQ evidence JSON:\n"
            f"{evidence_json}\n\n"
            "Write a short, helpful answer in Korean.",
        ),
    ])
    return str(response.content)


def faq_agent_node(state: ChatbotState) -> dict:
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=FAQ_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )

    query = state.get("enriched_query") or state.get("raw_query") or ""
    embedding_json = embed_query.invoke({"text": query})
    docs_json = search_documents.invoke({
        "embedding_json": embedding_json,
        "query_text": query,
        "top_k": _env_int("FAQ_RAG_MAX_RESULTS", 2),
    })
    evidence_json = rerank_documents.invoke({"docs_json": docs_json, "query": query})
    draft_text = _generate_faq_answer(query, evidence_json)
    update = {
        "messages": list(state["messages"]) + [{"role": "assistant", "content": draft_text}],
        "draft_text": draft_text,
        "retry_count": state["retry_count"],
        "category": state["category"],
        "routing_target": state["routing_target"],
        "reasoning_node": FAQ_POLICY.name,
    }

    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=FAQ_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={
            "draft_length": len(draft_text),
            "evidence_length": len(evidence_json),
        },
    )
    return update
