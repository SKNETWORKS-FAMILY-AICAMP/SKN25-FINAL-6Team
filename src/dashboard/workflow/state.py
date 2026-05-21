"""State schema for dashboard aggregate workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DashboardSection = Literal["overview", "risk", "quality", "all"]


class DashboardState(BaseModel):
    """Shared state passed through dashboard LangGraph nodes."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    section: DashboardSection = "all"
    days: int = 30
    window_start: datetime | None = None
    overview: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
