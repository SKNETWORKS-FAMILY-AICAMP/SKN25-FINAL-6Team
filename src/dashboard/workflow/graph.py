"""Service orchestration for dashboard aggregate computation."""

from __future__ import annotations

from typing import Any

from src.dashboard.ai import generate_dashboard_interpretation

from .nodes import (
    compute_overview_node,
    compute_quality_node,
    compute_risk_node,
    fetch_overview_node,
    fetch_quality_node,
    fetch_risk_node,
    load_window_node,
)
from .state import DashboardSection, DashboardState


class DashboardWorkflowRunner:
    """Thin compatibility runner that executes the dashboard pipeline in-process."""

    def invoke(self, state: DashboardState | dict[str, Any]) -> dict[str, Any]:
        current = DashboardState.model_validate(state)
        updates = load_window_node(current) or {}
        current = current.model_copy(update=updates)

        if current.section in {"overview", "all"}:
            updates = fetch_overview_node(current) or {}
            current = current.model_copy(update=updates)
            updates = compute_overview_node(current) or {}
            current = current.model_copy(update=updates)

        if current.section in {"risk", "all"}:
            updates = fetch_risk_node(current) or {}
            current = current.model_copy(update=updates)
            updates = compute_risk_node(current) or {}
            current = current.model_copy(update=updates)

        if current.section in {"quality", "all"}:
            updates = fetch_quality_node(current) or {}
            current = current.model_copy(update=updates)
            updates = compute_quality_node(current) or {}
            current = current.model_copy(update=updates)

        return current.model_dump()


def build_dashboard_graph(*, compile_graph: bool = True) -> DashboardWorkflowRunner:
    """Build the dashboard workflow runner.

    `compile_graph` is kept for backward compatibility with the former
    graph-based implementation.
    """

    _ = compile_graph
    return DashboardWorkflowRunner()


def run_dashboard_workflow(section: DashboardSection, days: int) -> dict[str, Any]:
    """Run the dashboard workflow and return the requested section."""

    app = build_dashboard_graph()
    result = app.invoke(DashboardState(section=section, days=days))
    state = DashboardState.model_validate(result)
    if section == "overview":
        overview = dict(state.overview)
        overview["ai_interpretation"] = generate_dashboard_interpretation("overview", overview)
        return overview
    if section == "risk":
        risk = dict(state.risk)
        risk["ai_interpretation"] = generate_dashboard_interpretation("risk", risk)
        return risk
    if section == "quality":
        quality = dict(state.quality)
        quality["ai_interpretation"] = generate_dashboard_interpretation("quality", quality)
        return quality
    overview = dict(state.overview)
    risk = dict(state.risk)
    quality = dict(state.quality)
    overview["ai_interpretation"] = generate_dashboard_interpretation("overview", overview)
    risk["ai_interpretation"] = generate_dashboard_interpretation("risk", risk)
    quality["ai_interpretation"] = generate_dashboard_interpretation("quality", quality)
    return {
        "window_days": state.days,
        "overview": overview,
        "risk": risk,
        "quality": quality,
    }
