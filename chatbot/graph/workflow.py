from __future__ import annotations

import sys
from pathlib import Path

from langgraph.graph import END, StateGraph

ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from chatbot.agents.bug_agent import bug_agent_node
from chatbot.agents.faq_agent import faq_agent_node
from chatbot.agents.orchestrator import orchestrator_node
from chatbot.agents.payment_agent import payment_agent_node
from chatbot.agents.voc_agent import voc_agent_node
from chatbot.constants import (
    FINAL_DECISION_AUTO,
    FINAL_DECISION_BLOCK,
    FINAL_DECISION_REVIEW,
    MAX_SAFETY_RETRY,
)
from chatbot.safety.safety_layer import safety_layer_node
from chatbot.schemas import ChatbotState


# ── HITL 노드 ─────────────────────────────────────────────────────────────────

def hitl_node(state: ChatbotState) -> dict:
    """BLOCK_RESPONSE / REVIEW_QUEUE → 운영 대시보드 에스컬레이션 기록."""
    return {"safety_passed": False}


# ── 라우팅 함수 ───────────────────────────────────────────────────────────────

def _route_by_category(state: ChatbotState) -> str:
    return state.get("category", "FAQ")


def _route_after_safety(state: ChatbotState) -> str:
    decision = state.get("final_decision", "")

    if decision == FINAL_DECISION_AUTO:
        return END

    if decision in (FINAL_DECISION_BLOCK, FINAL_DECISION_REVIEW):
        return "hitl"

    # SAFE_FALLBACK / MASKING — 재시도 or 고정 안내문으로 종료
    if state.get("retry_count", 0) >= MAX_SAFETY_RETRY:
        return END
    return state.get("category", "FAQ")


# ── 그래프 조립 ───────────────────────────────────────────────────────────────

workflow = StateGraph(ChatbotState)

workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("payment_agent", payment_agent_node)
workflow.add_node("bug_agent", bug_agent_node)
workflow.add_node("faq_agent", faq_agent_node)
workflow.add_node("voc_agent", voc_agent_node)
workflow.add_node("safety_layer", safety_layer_node)
workflow.add_node("hitl", hitl_node)

workflow.set_entry_point("orchestrator")

workflow.add_conditional_edges(
    "orchestrator",
    _route_by_category,
    {
        "결제": "payment_agent",
        "인게임버그": "bug_agent",
        "FAQ": "faq_agent",
        "VOC": "voc_agent",
    },
)

for _node in ("payment_agent", "bug_agent", "faq_agent", "voc_agent"):
    workflow.add_edge(_node, "safety_layer")

workflow.add_conditional_edges(
    "safety_layer",
    _route_after_safety,
    {
        "결제": "payment_agent",
        "인게임버그": "bug_agent",
        "FAQ": "faq_agent",
        "VOC": "voc_agent",
        "hitl": "hitl",
        END: END,
    },
)

workflow.add_edge("hitl", END)

graph = workflow.compile()
