from __future__ import annotations


def send_slack_alert(message: str) -> dict[str, str]:
    """Placeholder Slack sender until webhook integration is added."""
    return {"status": "skipped", "reason": "slack webhook is not configured", "message": message}

