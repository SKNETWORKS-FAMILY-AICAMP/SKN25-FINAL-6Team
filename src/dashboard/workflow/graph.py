"""LangGraph declaration for dashboard aggregate computation."""

from __future__ import annotations

from typing import Any

from .nodes import NODE_FUNCTIONS, route_after_overview, route_after_risk, route_after_window
from .state import DashboardSection, DashboardState


def build_dashboard_graph(*, compile_graph: bool = True):
    """Build the dashboard LangGraph."""

    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(DashboardState)
    for node_name, node_handler in NODE_FUNCTIONS.items():
        graph.add_node(node_name, node_handler)

    graph.add_edge(START, "load_window_node")
    graph.add_conditional_edges(
        "load_window_node",
        route_after_window,
        {
            "overview": "fetch_overview_node",
            "risk": "fetch_risk_node",
            "quality": "fetch_quality_node",
            "all": "fetch_overview_node",
        },
    )
    graph.add_edge("fetch_overview_node", "compute_overview_node")
    graph.add_conditional_edges(
        "compute_overview_node",
        route_after_overview,
        {
            "all": "fetch_risk_node",
            "stop": END,
        },
    )
    graph.add_edge("fetch_risk_node", "compute_risk_node")
    graph.add_conditional_edges(
        "compute_risk_node",
        route_after_risk,
        {
            "all": "fetch_quality_node",
            "stop": END,
        },
    )
    graph.add_edge("fetch_quality_node", "compute_quality_node")
    graph.add_edge("compute_quality_node", END)

    if compile_graph:
        return graph.compile()
    return graph


def run_dashboard_workflow(section: DashboardSection, days: int) -> dict[str, Any]:
    """Run the dashboard workflow and return the requested section."""

    app = build_dashboard_graph()
    result = app.invoke(DashboardState(section=section, days=days))
    state = DashboardState.model_validate(result)
    if section == "overview":
        return state.overview
    if section == "risk":
        return state.risk
    if section == "quality":
        return state.quality
    return {
        "window_days": state.days,
        "overview": state.overview,
        "risk": state.risk,
        "quality": state.quality,
    }
