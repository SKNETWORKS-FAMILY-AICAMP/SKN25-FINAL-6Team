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


def _is_voc_state(state: ChatbotState) -> bool:
    category = str(state.get("category") or "").strip().lower()
    return category == "voc" or state.get("reasoning_node") == "voc_agent"




def route_after_draft_persistence(state: ChatbotState) -> str:
    """Skip safety scoring for fixed VOC responses, otherwise run safety."""
    if _is_voc_state(state):
        return "final_response"
    return "safety_layer"


def route_after_safety(state: ChatbotState) -> str:
    """Return to the concrete category node on retry, or finish when safety passes/exhausts."""
    if _is_voc_state(state):
        return "final_response"
    if state.get("safety_action") == "MASKING":
        if state.get("retry_count", 0) <= MAX_MASKING_RETRY:
            return "draft_persistence"
        return "final_response"
    if state.get("safety_action") in {"BLOCK_RESPONSE", "SAFE_FALLBACK", "REVIEW_QUEUE"}:
        return "final_response"
    if state["safety_passed"]:
        return "final_response"
    if state["retry_count"] >= MAX_SAFETY_RETRY:
        return "final_response"
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
    target_node = CATEGORY_NODE_BY_NAME.get(category)
    dispatch_valid = target_node is not None

    return {
        "selected_category": category,
        "target_node": target_node or "voc_agent",
        "dispatch_valid": dispatch_valid,
        "dispatch_match": dispatch_valid,
        "latency_ms": round((perf_counter() - started_at) * 1000, 3),
    }

def route_after_preprocess(state: ChatbotState) -> str:
    if "prompt_injection" in (state.get("input_detected_labels") or []):
        return "final_response"
    return route_by_category(state)


def route_by_category(state: ChatbotState) -> str:
    started_at = perf_counter()
    dispatch = _trace_category_dispatch(state, started_at=started_at)

    if not dispatch["dispatch_valid"]:
        raise ValueError(
            f"unsupported category: {dispatch['selected_category']}. "
            f"allowed: {', '.join(sorted(CATEGORY_NODE_BY_NAME))}"
        )

    return dispatch["target_node"]