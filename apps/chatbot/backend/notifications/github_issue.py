from __future__ import annotations

import json
import os
from urllib import request
from urllib.error import HTTPError

from chatbot.observability.error_classifier import classify_error
from chatbot.observability.logger import EVENT_NOTIFICATION_FAILED, log_event


GITHUB_API_BASE_URL = "https://api.github.com"


def _github_labels() -> list[str]:
    raw_labels = os.getenv("GITHUB_ISSUE_LABELS", "bug,in-game,chatbot")
    return [label.strip() for label in raw_labels.split(",") if label.strip()]


def create_github_issue(title: str, body: str) -> dict[str, str]:
    """Create a GitHub issue for an in-game bug report; otherwise return mock result."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not token:
        return {"status": "mock", "reason": "github token is not configured", "message": body}
    if not repository:
        return {"status": "mock", "reason": "github repository is not configured", "message": body}

    try:
        payload = {
            "title": title,
            "body": body,
            "labels": _github_labels(),
        }
        req = request.Request(
            f"{GITHUB_API_BASE_URL}/repos/{repository}/issues",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "skn25-chatbot",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API HTTP {exc.code}: {response_body}") from exc

        data = json.loads(response_body)
        return {
            "status": "ok",
            "issue_number": str(data.get("number", "")),
            "issue_url": str(data.get("html_url", "")),
        }
    except Exception as exc:
        error_category = classify_error(exc)
        log_event(
            EVENT_NOTIFICATION_FAILED,
            tool_name="github_issue",
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
