from __future__ import annotations

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


def route_by_category(state: ChatbotState) -> str:
    # 1단계: 전처리에서 확정한 category를 실제 agent 노드 이름으로 변환한다.
    category = state["category"]
    return CATEGORY_NODE_BY_NAME.get(str(category), "voc_agent")


def route_after_draft_persistence(state: ChatbotState) -> str:
    # 2단계: VOC는 고정 응답이라 safety 검사를 생략하고, 나머지 category는 safety_layer로 보낸다.
    if _is_voc_state(state):
        return "final_response"
    return "safety_layer"


def route_after_safety(state: ChatbotState) -> str:
    # 3단계: safety 결과에 따라 마스킹 재저장, fallback/review/block, 재생성, 최종 응답을 결정한다.
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
