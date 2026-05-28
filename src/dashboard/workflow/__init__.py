"""Dashboard workflow helpers for aggregate computation."""

from __future__ import annotations

from typing import Any

from .service import DashboardWorkflowService, run_dashboard_workflow
from .state import DashboardState


def run_weekly_report_workflow(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .weekly_report.service import run_weekly_report_workflow as _run_weekly_report_workflow

    return _run_weekly_report_workflow(*args, **kwargs)


def start_weekly_report_scheduler() -> Any:
    try:
        from .weekly_report.scheduler import start_weekly_report_scheduler as _start_weekly_report_scheduler
    except ModuleNotFoundError:
        return None

    return _start_weekly_report_scheduler()


__all__ = [
    "DashboardState",
    "DashboardWorkflowService",
    "run_dashboard_workflow",
    "run_weekly_report_workflow",
    "start_weekly_report_scheduler",
]
