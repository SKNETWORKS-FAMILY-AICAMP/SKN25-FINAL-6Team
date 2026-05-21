from __future__ import annotations

import json
import os
from typing import Any

from chatbot.generation.prompts.orchestrator_prompt import ORCHESTRATOR_SYSTEM_PROMPT
from chatbot.schemas import ChatbotState, OrchestratorOutput
from chatbot.tools.db_tools import write_qa_ticket, write_ticket_analysis


def _normalize_text(text: str) -> str:
    """사용자 입력의 앞뒤 공백과 중복 공백을 정리해 분류하기 좋은 형태로 만든다."""
    return " ".join(text.strip().split())


def _classify_with_llm(ticket_id: int, enriched_query: str) -> OrchestratorOutput:
    """LLM structured output으로 카테고리와 라우팅 타깃을 판단한다."""
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not api_key or not model:
        raise RuntimeError("OpenAI settings are missing.")

    from langchain_openai import ChatOpenAI

    classifier = ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0,
    ).with_structured_output(OrchestratorOutput)

    return classifier.invoke([
        ("system", ORCHESTRATOR_SYSTEM_PROMPT),
        (
            "user",
            "Classify this ticket.\n"
            f"ticket_id: {ticket_id}\n"
            f"enriched_query: {enriched_query}",
        ),
    ])


def _classify(ticket_id: int, enriched_query: str) -> tuple[str, str, str, str]:
    """LLM structured output 결과를 그대로 state에 매핑한다."""
    result = _classify_with_llm(ticket_id, enriched_query)
    return result.category, result.routing_target, "llm", result.reason


def _require_stored_result(raw_result: str, *, operation: str, id_field: str) -> dict[str, Any]:
    result = json.loads(raw_result)
    if result.get("stored") and result.get(id_field) is not None:
        return result
    error_message = result.get("message") or result.get("error") or "unknown write failure"
    raise RuntimeError(f"{operation} failed before workflow could continue: {error_message}")


def orchestrator_node(state: ChatbotState) -> dict:
    """StateGraph의 orchestration 노드.

    사용자 문의를 정리하고 카테고리/라우팅 타깃을 결정한 뒤,
    QA 티켓과 분석 결과를 저장하고 다음 노드가 사용할 state 값을 반환한다.
    """
    ticket_id = state["ticket_id"]
    raw_query = state["raw_query"]
    enriched_query = _normalize_text(raw_query)
    category, routing_target, classification_method, classification_reason = _classify(ticket_id, enriched_query)

    write_qa_ticket.invoke({
        "payload": {
            "ticket_id": ticket_id,
            "user_id": state["user_id"],
            "account_id": state["account_id"],
            "session_id": state.get("session_id"),
            "raw_query": raw_query,
            "source_type": state["source_type"],
            "status": "open",
        },
    })
    analysis_result = _require_stored_result(write_ticket_analysis.invoke({
        "payload": {
            "ticket_id": ticket_id,
            "category": category,
            "responder_type": "AI",
            "enriched_query": enriched_query,
            "risk_level": "normal",
            "sentiment": "neutral",
            "routing_target": routing_target,
            "summary": classification_reason,
        },
    }), operation="write_ticket_analysis", id_field="analysis_id")
    analysis_id = analysis_result["analysis_id"]

    return {
        "ticket_id": ticket_id,
        "analysis_id": analysis_id,
        "enriched_query": enriched_query,
        "category": category,
        "routing_target": routing_target,
        "classification_method": classification_method,
        "classification_reason": classification_reason,
    }
