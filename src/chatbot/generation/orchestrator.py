from __future__ import annotations

import json
import os
from typing import Any

from chatbot.generation.prompts.orchestrator_prompt import ORCHESTRATOR_SYSTEM_PROMPT
from chatbot.schemas import ChatbotState, OrchestratorOutput, RoutingIntent
from chatbot.tools.db_tools import write_qa_ticket, write_ticket_analysis


PAYMENT_CATEGORY = "결제"
BUG_CATEGORY = "인게임/버그"
FAQ_CATEGORY = "FAQ"
VOC_CATEGORY = "VOC"

RAG_INTENTS = {
    "payment_how_to",
    "bug_how_to",
    "policy_question",
    "faq_question",
}
PAYMENT_OPERATION_INTENTS = {
    "payment_missing_item",
    "refund_request",
    "payment_dispute",
}
BUG_OPERATION_INTENTS = {
    "bug_account_specific",
}


def _normalize_text(text: str) -> str:
    """Normalize whitespace before routing."""
    return " ".join(text.strip().split())


def _normalize_intent_with_llm(enriched_query: str) -> RoutingIntent:
    """Normalize slangy user phrasing into a stable routing intent."""
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("ROUTING_INTENT_MODEL") or os.environ.get("LLM_MODEL")
    if not api_key or not model:
        raise RuntimeError("OpenAI settings are missing.")

    from langchain_openai import ChatOpenAI

    normalizer = ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0,
    ).with_structured_output(RoutingIntent)

    return normalizer.invoke(
        [
            (
                "system",
                "You normalize Korean game CS user inquiries before routing. "
                "Return a structured intent, not an answer. "
                "Map slang and mixed language into a concise Korean normalized_query. "
                "Set is_actionable=false when the user only expresses vague emotion, insult, praise, or dissatisfaction "
                "without a concrete question, feature, error, account/payment issue, or requested action. "
                "Set should_use_rag=true only when official FAQ, notice, policy, patch note, or guide documents can likely answer it. "
                "For vague non-actionable complaints, use intent=voc, should_use_rag=false, "
                "and set fallback_reason='low_information_complaint'. "
                "Examples: 'galaxy store 결제 어캐함?' -> intent=payment_how_to, "
                "normalized_query='갤럭시 스토어 결제 방법', is_actionable=true, should_use_rag=true. "
                "'스토리 초기화 어캐함?', '진행도 초기화 어캐함?', and '게임 진행도 리셋 어캐함?' "
                "are the same general FAQ intent: intent=faq_question, "
                "normalized_query='게임 진행도 리셋 방법', is_actionable=true, should_use_rag=true. "
                "'결제했는데 상품 안 들어옴' -> intent=payment_missing_item, "
                "is_actionable=true, requires_account_lookup=true, should_use_rag=false. "
                "'게임 실행 안 됨 어케함?' -> intent=bug_how_to, "
                "normalized_query='게임 실행 오류 해결 방법', is_actionable=true, should_use_rag=true. "
                "'게임 왜 이따위임?' -> intent=voc, normalized_query='게임 이용 불만', "
                "is_actionable=false, should_use_rag=false, fallback_reason='low_information_complaint'. "
                "Use requires_account_lookup for account-specific checks, refunds, disputes, "
                "missing paid items, or user-specific bug investigation.",
            ),
            ("user", enriched_query),
        ]
    )


def _route_from_intent(intent: RoutingIntent, account_id: int | None = None) -> tuple[str, str, str]:
    """Map normalized intent to workflow category/routing target."""
    intent_name = intent.intent
    requires_account_lookup = intent.requires_account_lookup

    if not intent.is_actionable and not intent.should_use_rag:
        return VOC_CATEGORY, "rag_reply", f"intent:{intent_name}; {intent.reason}"

    if intent.should_use_rag or intent_name in RAG_INTENTS:
        return FAQ_CATEGORY, "rag_reply", f"intent:{intent_name}; {intent.reason}"

    if intent_name == "voc":
        return VOC_CATEGORY, "rag_reply", f"intent:{intent_name}; {intent.reason}"

    if intent_name in PAYMENT_OPERATION_INTENTS or (
        requires_account_lookup and intent_name.startswith("payment_")
    ):
        return PAYMENT_CATEGORY, "urgent_alert", f"intent:{intent_name}; {intent.reason}"

    if intent_name in BUG_OPERATION_INTENTS or (
        requires_account_lookup and intent_name.startswith("bug_")
    ):
        return BUG_CATEGORY, "urgent_alert", f"intent:{intent_name}; {intent.reason}"

    return FAQ_CATEGORY, "rag_reply", f"intent:{intent_name}; default_rag"


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


def _classify(
    ticket_id: int,
    enriched_query: str,
    account_id: int | None = None,
) -> tuple[str, str, str, str, str, bool | None, bool | None, str | None]:
    """Map the classifier result into workflow state fields."""
    try:
        intent = _normalize_intent_with_llm(enriched_query)
    except Exception:
        intent = None

    if intent is not None:
        category, routing_target, reason = _route_from_intent(intent, account_id=account_id)
        normalized_query = _normalize_text(intent.normalized_query or enriched_query)
        return (
            category,
            routing_target,
            "llm_intent",
            reason,
            normalized_query,
            intent.is_actionable,
            intent.should_use_rag,
            intent.fallback_reason,
        )

    try:
        result = _classify_with_llm(ticket_id, enriched_query)
        return result.category, result.routing_target, "llm", result.reason, enriched_query, None, None, None
    except Exception:
        return (
            FAQ_CATEGORY,
            "rag_reply",
            "fallback",
            "intent_and_classifier_unavailable",
            enriched_query,
            None,
            None,
            None,
        )


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
    (
        category,
        routing_target,
        classification_method,
        classification_reason,
        normalized_query,
        is_actionable,
        should_use_rag,
        fallback_reason,
    ) = _classify(
        ticket_id,
        enriched_query,
        account_id=state.get("account_id"),
    )
    enriched_query = normalized_query

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
        "is_actionable": is_actionable,
        "should_use_rag": should_use_rag,
        "fallback_reason": fallback_reason,
    }
