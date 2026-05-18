from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_log_event(event_type: str, **payload: Any) -> dict[str, Any]:
    """Build a structured admin log event without binding to a logging backend yet."""
    return {
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }

