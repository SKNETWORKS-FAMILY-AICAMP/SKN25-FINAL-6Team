from __future__ import annotations

from chatbot.notifications.slack import send_slack_alert


def dispatch_urgent_alert(message: str) -> dict[str, str]:
    """Dispatch urgent chatbot events to configured notification channels."""
    return send_slack_alert(message)

