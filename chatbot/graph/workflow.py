from __future__ import annotations

from langgraph.graph import END, StateGraph

from chatbot.agents.bug_agent import bug_agent_node
from chatbot.agents.faq_agent import faq_agent_node
from chatbot.agents.orchestrator import orchestrator_node
from chatbot.agents.payment_agent import payment_agent_node
from chatbot.agents.voc_agent import voc_agent_node
from chatbot.constants import MAX_SAFETY_RETRY
from chatbot.response.final_response import final_response_node
from chatbot.safety.safety_layer import safety_layer_node
from chatbot.schemas import ChatbotState


def _route_by_category(state: ChatbotState) -> str:
    category = state.get("category") or "FAQ"
    if category == "결제":
        return "payment_agent"
    if category == "인게임버그":
        return "bug_agent"
    if category == "VOC":
        return "voc_agent"
    return "faq_agent"


def _route_after_safety(state: ChatbotState) -> str:
    if state.get("safety_passed"):
        return "final_response"
    if state.get("retry_count", 0) >= MAX_SAFETY_RETRY:
        return "final_response"
    return _route_by_category(state)


workflow = StateGraph(ChatbotState)

workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("payment_agent", payment_agent_node)
workflow.add_node("bug_agent", bug_agent_node)
workflow.add_node("faq_agent", faq_agent_node)
workflow.add_node("voc_agent", voc_agent_node)
workflow.add_node("safety_layer", safety_layer_node)
workflow.add_node("final_response", final_response_node)

workflow.set_entry_point("orchestrator")

workflow.add_conditional_edges(
    "orchestrator",
    _route_by_category,
    {
        "payment_agent": "payment_agent",
        "bug_agent": "bug_agent",
        "faq_agent": "faq_agent",
        "voc_agent": "voc_agent",
    },
)

for node_name in ("payment_agent", "bug_agent", "faq_agent", "voc_agent"):
    workflow.add_edge(node_name, "safety_layer")

workflow.add_conditional_edges(
    "safety_layer",
    _route_after_safety,
    {
        "payment_agent": "payment_agent",
        "bug_agent": "bug_agent",
        "faq_agent": "faq_agent",
        "voc_agent": "voc_agent",
        "final_response": "final_response",
    },
)

workflow.add_edge("final_response", END)

graph = workflow.compile()
