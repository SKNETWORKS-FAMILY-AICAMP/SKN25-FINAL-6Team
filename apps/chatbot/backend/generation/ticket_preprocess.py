from __future__ import annotations

from typing import Any

from chatbot.generation.response.fixed_responses import BLOCK_RESPONSE
from chatbot.repository.ticket_repository import save_qa_ticket
from chatbot.schemas import ChatbotState
from chatbot.utils.query_enrichment import normalize_query_text


SUPPORTED_CATEGORIES = {"payment", "bug", "faq", "voc"}
write_qa_ticket = save_qa_ticket


def _write_qa_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    target = write_qa_ticket
    if hasattr(target, "invoke"):
        return target.invoke({"payload": payload})
    return target(payload)


def _category_from_user_selection(value: Any) -> str:
    # 사용자가 선택한 category만 신뢰하고, 지원하지 않는 category는 초기에 차단한다.
    category = str(value or "").strip().lower()
    if not category:
        raise ValueError("category is required for chatbot routing")
    if category not in SUPPORTED_CATEGORIES:
        allowed = ", ".join(sorted(SUPPORTED_CATEGORIES))
        raise ValueError(f"unsupported category: {category}. allowed: {allowed}")
    return category


def ticket_preprocess_node(state: ChatbotState) -> dict:
    # 1단계: 마스킹된 문의를 검색/분류에 쓰기 좋은 normalized_query로 정리한다.
    ticket_id = state["ticket_id"]
    raw_query = state["raw_query"]
    masked_content = state.get("masked_content") or raw_query
    category = _category_from_user_selection(state.get("category"))
    normalized_query = normalize_query_text(masked_content)
    routing_target = state.get("routing_target") or ("bug_agent" if category == "bug" else "rag_reply")
    should_use_rag = state.get("should_use_rag")
    if should_use_rag is None:
        should_use_rag = category == "faq"

    # 2단계: 원문 문의는 qa_ticket에 저장하고, 이후 노드는 state의 normalized_query를 사용한다.
    _write_qa_ticket(
        {
            "ticket_id": ticket_id,
            "user_id": state["user_id"],
            "account_id": state["account_id"],
            "session_id": state.get("session_id"),
            "raw_query": raw_query,
            "source_type": state["source_type"],
            "status": "pending",
        }
    )

    if "prompt_injection" in (state.get("input_detected_labels") or []):
        return {
            "ticket_id": ticket_id,
            "normalized_query": normalized_query,
            "category": category,
            "routing_target": routing_target,
            "is_actionable": False,
            "should_use_rag": False,
            "fallback_reason": "prompt_injection_detected",
            "draft_text": BLOCK_RESPONSE,
            "safety_action": "BLOCK_RESPONSE",
            "safety_passed": False,
            "retry_count": 0,
        }

    # 3단계: 선택 category와 RAG 사용 여부를 다음 라우팅 노드가 판단할 수 있게 넘긴다.
    return {
        "ticket_id": ticket_id,
        "normalized_query": normalized_query,
        "ui_category": state.get("ui_category"),
        "sub_category": state.get("sub_category"),
        "category": category,
        "routing_target": routing_target,
        "fallback_routing_target": state.get("fallback_routing_target"),
        "is_actionable": True,
        "should_use_rag": should_use_rag,
        "fallback_reason": None,
    }
