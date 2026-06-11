from __future__ import annotations

import json
import os
from urllib import request
from urllib.error import HTTPError

from chatbot.observability.error_classifier import classify_error
from chatbot.observability.logger import EVENT_NOTIFICATION_FAILED, log_event


SLACK_API_BASE_URL = "https://slack.com/api"


# Slack Web API 호출 공통 helper다.
# HTTP/API 실패는 예외로 올리고, 상위 send_slack_alert가 운영 로그로 남긴다.
def _post_slack_api(method: str, token: str, payload: dict[str, str]) -> dict[str, object]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        f"{SLACK_API_BASE_URL}/{method}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Slack API HTTP {exc.code}: {response_body}") from exc

    data = json.loads(response_body)
    if not data.get("ok"):
        raise RuntimeError(f"Slack API {method} failed: {data.get('error', 'unknown_error')}")
    return data


# REVIEW_QUEUE나 urgent_alert 상황에서 운영 Slack 채널로 알림을 보낸다.
def send_slack_alert(message: str) -> dict[str, str]:
    bot_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    channel_id = os.getenv("SLACK_CHANNEL_ID", "").strip()
    if not bot_token:
        return {"status": "mock", "reason": "slack bot token is not configured", "message": message}
    if not channel_id:
        return {"status": "mock", "reason": "slack channel id is not configured", "message": message}

    try:
        post_result = _post_slack_api(
            "chat.postMessage",
            bot_token,
            {"channel": channel_id, "text": message},
        )
        return {
            "status": "ok",
            "channel_id": channel_id,
            "message_ts": str(post_result.get("ts", "")),
        }
    except Exception as exc:
        error_category = classify_error(exc)
        log_event(
            EVENT_NOTIFICATION_FAILED,
            tool_name="slack",
            status="error",
            error_message=str(exc),
            error_category=error_category,
            metadata={"error_type": type(exc).__name__, "error_category": error_category},
        )
        return {
            "status": "error",
            "error": type(exc).__name__,
            "error_category": error_category,
            "message": str(exc),
        }
