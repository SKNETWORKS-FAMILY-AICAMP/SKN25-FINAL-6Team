from __future__ import annotations

import json
import os
from typing import Any

from chatbot.generation.prompts.orchestrator_prompt import ORCHESTRATOR_SYSTEM_PROMPT
from chatbot.schemas import ChatbotState, OrchestratorOutput
from chatbot.tools.db_tools import write_qa_ticket, write_ticket_analysis


PAYMENT_CATEGORY = "결제"
BUG_CATEGORY = "인게임/버그"
FAQ_CATEGORY = "FAQ"
VOC_CATEGORY = "VOC"


def _normalize_text(text: str) -> str:
    """Normalize whitespace before routing."""
    return " ".join(text.strip().split())


def _rule_based_route(enriched_query: str, account_id: int | None = None) -> tuple[str, str, str] | None:
    """Handle high-signal payment routing cases before the LLM classifier."""
    query = enriched_query.lower()

    payment_terms = ("결제", "환불", "구매", "스토어", "갤럭시", "google play", "구글플레이", "원스토어")
    payment_action_terms = (
        "안 들어",
        "안들어",
        "미지급",
        "누락",
        "취소",
        "환불",
        "내역",
        "확인해",
        "확인해줘",
        "처리",
    )
    how_to_terms = ("방법", "어떻게", "어디서", "알려", "안내", "정책", "기준", "절차", "가능", "되나요")

    has_payment = any(term in query for term in payment_terms)
    if not has_payment:
        return None

    has_action = any(term in query for term in payment_action_terms)
    has_how_to = any(term in query for term in how_to_terms)

    if has_action or account_id is not None:
        return PAYMENT_CATEGORY, "urgent_alert", "payment_action_or_account_specific"

    if has_how_to:
        return FAQ_CATEGORY, "rag_reply", "payment_policy_or_how_to"

    return FAQ_CATEGORY, "rag_reply", "payment_general_guidance"


def _classify_with_llm(ticket_id: int, enriched_query: str) -> OrchestratorOutput:
    """Classify category/routing target with structured LLM output."""
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

    return classifier.invoke(
        [
            ("system", ORCHESTRATOR_SYSTEM_PROMPT),
            (
                "user",
                "Classify this ticket.\n"
                f"ticket_id: {ticket_id}\n"
                f"enriched_query: {enriched_query}",
            ),
        ]
    )


def _classify(ticket_id: int, enriched_query: str, account_id: int | None = None) -> tuple[str, str, str, str]:
    """Map the classifier result into workflow state fields."""
    rule_result = _rule_based_route(enriched_query, account_id=account_id)
    if rule_result is not None:
        category, routing_target, reason = rule_result
        return category, routing_target, "rule", reason

    result = _classify_with_llm(ticket_id, enriched_query)
    return result.category, result.routing_target, "llm", result.reason


def _require_stored_result(raw_result: str, *, operation: str, id_field: str) -> dict[str, Any]:
    result = json.loads(raw_result)
    if result.get("stored") and result.get(id_field) is not None:
        return result
    error_message = result.get("message") or result.get("error") or "unknown write failure"
    raise RuntimeError(f"{operation} failed before workflow could continue: {error_message}")


def orchestrator_node(state: ChatbotState) -> dict:
    """Normalize the inquiry, classify routing, persist ticket analysis, and return state updates."""
    ticket_id = state["ticket_id"]
    raw_query = state["raw_query"]
    enriched_query = _normalize_text(raw_query)
    category, routing_target, classification_method, classification_reason = _classify(
        ticket_id,
        enriched_query,
        account_id=state.get("account_id"),
    )

    write_qa_ticket.invoke(
        {
            "payload": {
                "ticket_id": ticket_id,
                "user_id": state["user_id"],
                "account_id": state["account_id"],
                "session_id": state.get("session_id"),
                "raw_query": raw_query,
                "source_type": state["source_type"],
                "status": "open",
            },
        }
    )
    analysis_result = _require_stored_result(
        write_ticket_analysis.invoke(
            {
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
            }
        ),
        operation="write_ticket_analysis",
        id_field="analysis_id",
    )
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
