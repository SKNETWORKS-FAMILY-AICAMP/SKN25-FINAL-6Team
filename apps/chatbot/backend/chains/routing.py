from __future__ import annotations

from time import perf_counter
from typing import Any

from langsmith import traceable

from chatbot.constants import MAX_MASKING_RETRY, MAX_SAFETY_RETRY
from chatbot.schemas import ChatbotState


CATEGORY_NODE_BY_NAME = {
    "payment": "payment_agent",
    "bug": "bug_agent",
    "faq": "faq_agent",
    "voc": "voc_agent",
}

ROUTING_NODE_BY_TARGET = {
    "payment_agent": "payment_agent",
    "bug_agent": "bug_agent",
    "faq_agent": "faq_agent",
    "voc_agent": "voc_agent",
    "rag_reply": "faq_agent",
}


def _is_voc_state(state: ChatbotState) -> bool:
    category = str(state.get("category") or "").strip().lower()
    return category == "voc" or state.get("reasoning_node") == "voc_agent"


def route_after_draft_persistence(state: ChatbotState) -> str:
    # VOC는 고정 감사 응답이므로 safety 검사를 생략하고, 나머지 답변은 safety_layer로 보낸다.
    if _is_voc_state(state):
        return "ticket_completion"
    if (
        state.get("reasoning_node") == "bug_agent"
        and state.get("bug_collection_status") in {"collecting", "ready_for_review"}
        and not state.get("retrieved_documents")
    ):
        return "ticket_completion"
    return "safety_layer"


def route_after_safety(state: ChatbotState) -> str:
    # safety 결과에 따라 재저장, 재생성, fallback/review/block, 최종 응답 경로를 결정한다.
    if _is_voc_state(state):
        return "ticket_completion"
    if state.get("safety_action") == "MASKING":
        if state.get("retry_count", 0) <= MAX_MASKING_RETRY:
            return "draft_persistence"
        return "ticket_completion"
    if state.get("safety_action") in {"BLOCK_RESPONSE", "SAFE_FALLBACK", "REVIEW_REQUIRED"}:
        return "ticket_completion"
    if state["safety_passed"]:
        return "ticket_completion"
    if state["retry_count"] >= MAX_SAFETY_RETRY:
        return "ticket_completion"
    return route_by_category(state)


def _summarize_dispatch_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    state = inputs.get("state") or {}
    return {
        "ticket_id": state.get("ticket_id"),
        "session_id": state.get("session_id"),
        "selected_category": state.get("category"),
        "routing_target": state.get("routing_target"),
    }


def _summarize_dispatch_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    return outputs


@traceable(
    name="category_dispatch",
    run_type="chain",
    tags=["chatbot", "routing", "dispatch"],
    process_inputs=_summarize_dispatch_inputs,
    process_outputs=_summarize_dispatch_outputs,
)
def _trace_category_dispatch(state: ChatbotState, *, started_at: float) -> dict[str, Any]:
    category = str(state.get("category") or "").strip().lower()
    routing_target = str(state.get("routing_target") or "").strip().lower()
    target_node = ROUTING_NODE_BY_TARGET.get(routing_target) or CATEGORY_NODE_BY_NAME.get(category)
    dispatch_valid = target_node is not None

    return {
        "selected_category": category,
        "routing_target": routing_target,
        "target_node": target_node or "voc_agent",
        "dispatch_valid": dispatch_valid,
        "dispatch_match": dispatch_valid,
        "latency_ms": round((perf_counter() - started_at) * 1000, 3),
    }


def route_after_preprocess(state: ChatbotState) -> str:
    # prompt injection은 agent에 넘기지 않고 전처리 단계의 block 응답으로 바로 마무리한다.
    if "prompt_injection" in (state.get("input_detected_labels") or []):
        return "ticket_completion"
    return route_by_category(state)


def route_by_category(state: ChatbotState) -> str:
    # UI/전처리에서 정해진 category 또는 routing_target을 실제 agent 노드명으로 변환한다.
    started_at = perf_counter()
    dispatch = _trace_category_dispatch(state, started_at=started_at)

    if not dispatch["dispatch_valid"]:
        raise ValueError(
            f"unsupported category: {dispatch['selected_category']}. "
            f"allowed: {', '.join(sorted(CATEGORY_NODE_BY_NAME))}"
        )

    return dispatch["target_node"]
