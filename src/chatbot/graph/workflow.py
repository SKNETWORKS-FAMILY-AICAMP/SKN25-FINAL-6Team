from __future__ import annotations

from langgraph.graph import END, StateGraph

from chatbot.agents.bug_agent import bug_agent_node
from chatbot.agents.faq_agent import faq_agent_node
from chatbot.agents.orchestrator import orchestrator_node
from chatbot.agents.payment_agent import payment_agent_node
from chatbot.agents.voc_agent import voc_agent_node
from chatbot.graph.persistence import draft_persistence_node
from chatbot.graph.routing import route_after_safety, route_by_category
from chatbot.response.final_response import final_response_node
from chatbot.safety.safety_layer import safety_layer_node
from chatbot.schemas import ChatbotState


workflow = StateGraph(ChatbotState)

workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("payment_agent", payment_agent_node)
workflow.add_node("bug_agent", bug_agent_node)
workflow.add_node("faq_agent", faq_agent_node)
workflow.add_node("voc_agent", voc_agent_node)
workflow.add_node("draft_persistence", draft_persistence_node)
workflow.add_node("safety_layer", safety_layer_node)
workflow.add_node("final_response", final_response_node)

workflow.set_entry_point("orchestrator")

workflow.add_conditional_edges(
    "orchestrator",
    route_by_category,
    {
        "payment_agent": "payment_agent",
        "bug_agent": "bug_agent",
        "faq_agent": "faq_agent",
        "voc_agent": "voc_agent",
    },
)

for node_name in ("payment_agent", "bug_agent", "faq_agent"):
    workflow.add_edge(node_name, "draft_persistence")
workflow.add_edge("draft_persistence", "safety_layer")
workflow.add_edge("voc_agent", "final_response")

workflow.add_conditional_edges(
    "safety_layer",
    route_after_safety,
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
