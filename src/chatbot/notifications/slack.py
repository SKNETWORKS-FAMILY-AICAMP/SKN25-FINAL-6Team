from __future__ import annotations

import json
import os
from urllib import request

from chatbot.observability.error_classifier import classify_error
from chatbot.observability.logger import EVENT_NOTIFICATION_FAILED, log_event


def send_slack_alert(message: str) -> dict[str, str]:
    """Send Slack alert if SLACK_WEBHOOK_URL is configured; otherwise return mock result."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {"status": "mock", "reason": "slack webhook is not configured", "message": message}

    try:
        body = json.dumps({"text": message}, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=5) as response:
            return {"status": "ok", "http_status": str(response.status)}
    except Exception as exc:
        error_category = classify_error(exc)
        log_event(
            EVENT_NOTIFICATION_FAILED,
            tool_name="slack",
            status="error",
            error_message=str(exc),
            metadata={"error_type": type(exc).__name__, "error_category": error_category},
        )
        return {
            "status": "error",
            "error": type(exc).__name__,
            "error_category": error_category,
            "message": str(exc),
        }
