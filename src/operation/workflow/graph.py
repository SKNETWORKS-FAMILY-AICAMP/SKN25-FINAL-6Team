"""LangGraph declaration for operation ticket processing."""

from __future__ import annotations

from .nodes import (
    CONTEXT_NODE_BY_ROUTE,
    NODE_FUNCTIONS,
    route_after_save_draft,
    route_by_approval,
    route_by_human_decision,
    route_by_query,
    route_by_target,
)
from .state import OperationState


TARGET_ROUTE_TARGETS = {
    "rag_reply": "rag_retrieve_node",
    "urgent_alert": "urgent_draft_node",
}

APPROVAL_ROUTE_TARGETS = {
    "approved": "publish_final_answer_node",
    "human_review": "human_review_node",
    "urgent_alert": "urgent_alert_node",
}

HUMAN_DECISION_TARGETS = {
    "approved": "publish_final_answer_node",
    "reject": "retry_routing_node",
    "edit": "edit_answer_node",
}

SAVE_DRAFT_TARGETS = {
    "save_evidence_docs": "save_evidence_docs_node",
    "approval_gate": "approval_gate_node",
}

CONDITIONAL_EDGES = {
    "query_router": ("route_by_query", CONTEXT_NODE_BY_ROUTE),
    "save_analysis": ("route_by_target", TARGET_ROUTE_TARGETS),
    "save_draft_node": ("route_after_save_draft", SAVE_DRAFT_TARGETS),
    "save_safety_result_node": ("route_by_approval", APPROVAL_ROUTE_TARGETS),
    "human_review_node": ("route_by_human_decision", HUMAN_DECISION_TARGETS),
}

GRAPH_EDGES = (
    ("START", "load_ticket"),
    ("load_ticket", "query_router"),
    ("payment_context_node", "analyze_ticket"),
    ("refund_context_node", "analyze_ticket"),
    ("item_delivery_context_node", "analyze_ticket"),
    ("gacha_context_node", "analyze_ticket"),
    ("policy_context_node", "analyze_ticket"),
    ("abuse_context_node", "analyze_ticket"),
    ("outage_context_node", "analyze_ticket"),
    ("analyze_ticket", "save_analysis"),
    ("rag_retrieve_node", "generate_answer_node"),
    ("generate_answer_node", "save_draft_node"),
    ("save_draft_node", "save_evidence_docs_node"),
    ("save_evidence_docs_node", "approval_gate_node"),
    ("urgent_draft_node", "save_draft_node"),
    ("approval_gate_node", "save_safety_result_node"),
    ("retry_routing_node", "query_router"),
    ("edit_answer_node", "save_final_edit_node"),
    ("save_final_edit_node", "publish_final_answer_node"),
    ("publish_final_answer_node", "END"),
    ("urgent_alert_node", "END"),
)


def build_operation_graph(*, compile_graph: bool = True):
    """Build the operation LangGraph from the architecture Mermaid diagram.

    The current repository does not pin LangGraph yet, so the import is delayed
    until this builder is called. State and node declarations remain importable
    without the optional runtime dependency.
    """

    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(OperationState)
    for node_name, node_handler in NODE_FUNCTIONS.items():
        graph.add_node(node_name, node_handler)

    graph.add_edge(START, "load_ticket")
    graph.add_edge("load_ticket", "query_router")
    graph.add_conditional_edges("query_router", route_by_query, CONTEXT_NODE_BY_ROUTE)

    for context_node in CONTEXT_NODE_BY_ROUTE.values():
        graph.add_edge(context_node, "analyze_ticket")

    graph.add_edge("analyze_ticket", "save_analysis")
    graph.add_conditional_edges("save_analysis", route_by_target, TARGET_ROUTE_TARGETS)

    graph.add_edge("rag_retrieve_node", "generate_answer_node")
    graph.add_edge("generate_answer_node", "save_draft_node")
    graph.add_conditional_edges(
        "save_draft_node",
        route_after_save_draft,
        SAVE_DRAFT_TARGETS,
    )
    graph.add_edge("save_evidence_docs_node", "approval_gate_node")
    graph.add_edge("urgent_draft_node", "save_draft_node")

    graph.add_edge("approval_gate_node", "save_safety_result_node")
    graph.add_conditional_edges(
        "save_safety_result_node",
        route_by_approval,
        APPROVAL_ROUTE_TARGETS,
    )

    graph.add_conditional_edges(
        "human_review_node",
        route_by_human_decision,
        HUMAN_DECISION_TARGETS,
    )
    graph.add_edge("retry_routing_node", "query_router")
    graph.add_edge("edit_answer_node", "save_final_edit_node")
    graph.add_edge("save_final_edit_node", "publish_final_answer_node")
    graph.add_edge("publish_final_answer_node", END)
    graph.add_edge("urgent_alert_node", END)

    if compile_graph:
        return graph.compile()
    return graph
