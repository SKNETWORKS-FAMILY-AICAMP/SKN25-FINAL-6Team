"""Dashboard workflow helpers for aggregate computation."""

from __future__ import annotations

from typing import Any

from .service import DashboardWorkflowService, run_dashboard_workflow


def run_weekly_report_workflow(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .weekly_report.service import run_weekly_report_workflow as _run_weekly_report_workflow

    return _run_weekly_report_workflow(*args, **kwargs)


__all__ = [
    "DashboardWorkflowService",
    "run_dashboard_workflow",
    "run_weekly_report_workflow",
]
