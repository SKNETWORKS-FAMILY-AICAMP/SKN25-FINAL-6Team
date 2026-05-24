"""State schema for the weekly dashboard report workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WeeklyReportState(BaseModel):
    """Shared state passed through the weekly report workflow."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    days: int = 7
    window_start: datetime | None = None
    window_end: datetime | None = None
    previous_window_start: datetime | None = None
    previous_window_end: datetime | None = None
    send_to_slack: bool = False
    slack_channel: str | None = None
    slack_comment: str | None = None
    dashboard_summary: dict[str, Any] = Field(default_factory=dict)
    current_rows: list[dict[str, Any]] = Field(default_factory=list)
    previous_rows: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime | None = None
    report: dict[str, Any] = Field(default_factory=dict)
    pdf_bytes: bytes | None = None
    slack_result: dict[str, Any] = Field(default_factory=dict)
