"""LangGraph declaration for the operation workflow with pre-finalize review."""

from __future__ import annotations

from .nodes import NODE_FUNCTIONS
from .state import OperationState


def build_operation_graph(*, compile_graph: bool = True):
    """Build the operation workflow graph."""

    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(OperationState)
    for node_name, node_handler in NODE_FUNCTIONS.items():
        graph.add_node(node_name, node_handler)

    graph.add_edge(START, "load_ticket")
    graph.add_edge("load_ticket", "intake_agent")
    graph.add_edge("intake_agent", "context_agent")
    graph.add_edge("context_agent", "drafting_agent")
    graph.add_edge("drafting_agent", "review_agent")
    graph.add_edge("review_agent", "review")
    graph.add_conditional_edges(
        "review",
        lambda state: state.get("human_decision") if isinstance(state, dict) else state.human_decision,
        {
            "approved": "finalize",
            "edit": "finalize",
            "regenerate": "intake_agent",
        },
    )
    graph.add_edge("finalize", END)

    if compile_graph:
        return graph.compile()
    return graph
