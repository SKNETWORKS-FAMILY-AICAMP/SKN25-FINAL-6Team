from __future__ import annotations

import os
import re
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agent import invoke_bug_agent
from generation.faq_agent import run_faq_rag
from generation.drafting_agent import build_draft_update
from generation.policies import BUG_POLICY
from observability.langfuse import link_chatbot_trace
from observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from schemas import ChatbotState
from utils.config_loader import get_list_config, get_text_config
from common.observability.langfuse import get_langchain_config, observe_if_enabled
from common.observability.logger import record_chat_model_usage


BugIntentType = Literal["BUG_REPORT", "NOT_BUG"]


class BugIntentResult(BaseModel):
    intent_type: BugIntentType
    confidence: float = Field(ge=0.0, le=1.0)
    method: Literal["rule", "llm", "fallback"]
    reason: str = ""


class _BugIntentLLMOutput(BaseModel):
    intent_type: BugIntentType
    reason: str = ""


BUG_INTENT_RULES = "rules/bug_intent.yaml"
BUG_REPORT_PATTERNS = get_list_config(BUG_INTENT_RULES, "bug_report_patterns")
NOT_BUG_PATTERNS = get_list_config(BUG_INTENT_RULES, "not_bug_patterns")
BUG_INTENT_CLASSIFIER_PROMPT = get_text_config("prompts/bug_intent_classifier.yaml", "template")
BUG_OFF_TOPIC_RESPONSE = get_text_config("responses_bug.yaml", "off_topic")
BUG_ACCEPTED_RESPONSE = get_text_config("responses_bug.yaml", "accepted")


def _active_query(state: ChatbotState) -> str:
    return str(state.get("normalized_query") or state.get("raw_query") or "").strip()


def _normalize_intent_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _matches_intent_patterns(patterns: tuple[str, ...], text: str) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def _classify_bug_intent_by_rule(text: str) -> BugIntentResult | None:
    normalized = _normalize_intent_text(text)
    if not normalized:
        return BugIntentResult(
            intent_type="NOT_BUG",
            confidence=0.75,
            method="fallback",
            reason="empty query is not a bug report",
        )

    bug_hits = _matches_intent_patterns(BUG_REPORT_PATTERNS, normalized)
    not_bug_hits = _matches_intent_patterns(NOT_BUG_PATTERNS, normalized)

    if bug_hits:
        return BugIntentResult(
            intent_type="BUG_REPORT",
            confidence=0.9,
            method="rule",
            reason=f"bug symptom pattern matched: {bug_hits[0]}",
        )
    if not_bug_hits:
        return BugIntentResult(
            intent_type="NOT_BUG",
            confidence=0.86,
            method="rule",
            reason=f"non-bug support pattern matched: {not_bug_hits[0]}",
        )
    return None


def _bug_intent_llm_enabled() -> bool:
    value = os.environ.get("BUG_INTENT_LLM_ENABLED", "false").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _classify_bug_intent_by_llm(text: str) -> BugIntentResult | None:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key or not _bug_intent_llm_enabled():
        return None

    model = os.environ.get("BUG_INTENT_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
    classifier = llm.with_structured_output(_BugIntentLLMOutput, include_raw=True)
    raw_result = classifier.invoke(
        [
            {
                "role": "system",
                "content": BUG_INTENT_CLASSIFIER_PROMPT,
            },
            {"role": "user", "content": text},
        ],
        config=get_langchain_config(),
    )
    record_chat_model_usage("bug_intent_classifier", model, raw_result.get("raw"))
    result = raw_result.get("parsed")
    if result is None:
        return None
    return BugIntentResult(
        intent_type=result.intent_type,
        confidence=0.8,
        method="llm",
        reason=result.reason,
    )


def classify_bug_intent(text: str) -> dict[str, object]:
    rule_result = _classify_bug_intent_by_rule(text)
    if rule_result is not None:
        return dict(rule_result)

    try:
        llm_result = _classify_bug_intent_by_llm(text)
    except Exception as exc:
        llm_result = BugIntentResult(
            intent_type="BUG_REPORT",
            confidence=0.55,
            method="fallback",
            reason=f"LLM intent classifier failed; defaulted to bug report: {exc.__class__.__name__}",
        )
    if llm_result is not None:
        return dict(llm_result)

    return BugIntentResult(
        intent_type="BUG_REPORT",
        confidence=0.55,
        method="fallback",
        reason="no high-confidence rule hit and LLM fallback unavailable",
    ).dict()


def _state_with_bug_intent(state: ChatbotState, bug_intent: dict[str, object]) -> dict[str, Any]:
    updated = dict(state)
    updated["bug_intent"] = bug_intent
    guidance = (
        "Bug intent precheck: this message is classified as BUG_REPORT. "
        "Do not use the off-topic response unless the user is clearly asking about a non-bug support area."
    )
    messages = list(updated.get("messages") or [])
    if messages:
        messages = [{"role": "system", "content": guidance}, *messages]
    else:
        messages = [{"role": "system", "content": guidance}]
    updated["messages"] = messages
    return updated


def _base_bug_update(
    state: ChatbotState,
    bug_intent: dict[str, object],
    *,
    draft_text: str,
    safety_action: str,
    review_required: bool,
) -> dict[str, Any]:
    return {
        "draft_text": draft_text,
        "retry_count": state["retry_count"],
        "category": state["category"],
        "routing_target": state["routing_target"],
        "reasoning_node": BUG_POLICY.name,
        "bug_intent": bug_intent,
        "safety_action": safety_action,
        "safety_passed": True,
        "review_required": review_required,
    }


def _build_bug_off_topic_update(state: ChatbotState, bug_intent: dict[str, object]) -> dict[str, Any]:
    return _base_bug_update(
        state,
        bug_intent,
        draft_text=BUG_OFF_TOPIC_RESPONSE,
        safety_action="AUTO_RESPONSE",
        review_required=False,
    )


def _build_bug_review_update(state: ChatbotState, bug_intent: dict[str, object]) -> dict[str, Any]:
    return _base_bug_update(
        state,
        bug_intent,
        draft_text=BUG_ACCEPTED_RESPONSE,
        safety_action="REVIEW_REQUIRED",
        review_required=True,
    )


def _build_bug_agent_update(state: ChatbotState, bug_intent: dict[str, object]) -> dict[str, Any]:
    result = invoke_bug_agent(_state_with_bug_intent(state, bug_intent))
    return {
        **build_draft_update(state, result, BUG_POLICY.name),
        "bug_intent": bug_intent,
        "review_required": True,
    }


def _build_bug_rag_update(state: ChatbotState, bug_intent: dict[str, object]) -> dict[str, Any]:
    rag_result = run_faq_rag(state, retry_on_low_evidence=False)
    documents = rag_result.get("retrieved_documents") or []
    return {
        "draft_text": rag_result["draft_text"],
        "retry_count": state["retry_count"],
        "category": state["category"],
        "routing_target": state["routing_target"],
        "reasoning_node": BUG_POLICY.name,
        "bug_intent": bug_intent,
        "retrieved_documents": documents,
        "retrieved_count": len(documents),
        "retrieval_query": rag_result["retrieval_query"],
        "retrieval_enrichment": rag_result.get("retrieval_enrichment"),
        "retrieval_cache_enabled": state.get("retrieval_cache_enabled"),
        "retrieval_cache_hit": state.get("retrieval_cache_hit"),
        "retrieval_cache_backend": state.get("retrieval_cache_backend"),
        "retrieval_cache_key_hash": state.get("retrieval_cache_key_hash"),
        "retrieval_cache_ttl": state.get("retrieval_cache_ttl"),
        "faq_failure_reason": rag_result["faq_failure_reason"],
        "safety_action": "AUTO_RESPONSE",
        "safety_passed": True,
        "review_required": False,
    }


def bug_agent_node(state: ChatbotState) -> dict:
    # 1단계: 버그 문의는 자동 확정 답변보다 재현 정보 수집/검토 안내 중심으로 초안을 만든다.
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )
    bug_intent = (
        {"intent_type": "BUG_REPORT", "confidence": 1.0, "method": "conversation", "reason": "bug report form submitted"}
        if state.get("bug_report_form")
        else classify_bug_intent(_active_query(state))
    )

    if bug_intent.get("intent_type") == "NOT_BUG":
        update = _build_bug_off_topic_update(state, bug_intent)
    else:
        if state.get("bug_report_form"):
            update = _build_bug_review_update(state, bug_intent)
        else:
            update = _build_bug_rag_update(state, bug_intent)

    # 2단계: 생성된 버그 초안 길이를 기록하고 공통 draft_persistence 노드로 넘긴다.
    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={"draft_length": len(update.get("draft_text") or "")},
    )
    return update


_original_bug_agent_node = bug_agent_node


@observe_if_enabled(
    name="bug_agent",
    as_type="chain",
    tags=["chatbot", "feature:generation", "bug"],
)
def bug_agent_node(state: ChatbotState) -> dict:
    link_chatbot_trace(
        state,
        tags=["feature:generation", "bug"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "query": state.get("normalized_query") or state.get("raw_query"),
            "routing_target": state.get("routing_target"),
            "bug_report_form_present": bool(state.get("bug_report_form")),
        },
    )
    result = _original_bug_agent_node(state)
    link_chatbot_trace(
        state,
        tags=["feature:generation", "bug"],
        metadata_source={**state, **result},
        output_payload=result,
    )
    return result
