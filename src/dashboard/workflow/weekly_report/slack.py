"""Slack delivery helpers for the weekly dashboard report."""

from __future__ import annotations

import io
import os
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .errors import SlackReportError


def _resolve_channel_id(client: WebClient, channel: str) -> str:
    """Resolve a Slack channel reference to a channel ID."""

    raw = (channel or "").strip()
    if not raw:
        raise SlackReportError("Slack channel is required")
    if raw[0] in {"C", "G", "D"} and raw[1:].isalnum():
        return raw

    normalized_name = raw[1:] if raw.startswith("#") else raw
    cursor = ""
    while True:
        response = client.conversations_list(
            exclude_archived=True,
            limit=200,
            types="public_channel,private_channel",
            cursor=cursor or None,
        )
        channels = response.get("channels") or []
        for item in channels:
            name = str(item.get("name") or "").strip()
            if name == normalized_name:
                channel_id = str(item.get("id") or "")
                if channel_id:
                    return channel_id

        cursor = str((response.get("response_metadata") or {}).get("next_cursor") or "")
        if not cursor:
            break

    raise SlackReportError(f"channel not found: {raw}. use channel ID like C0123456789 or invite bot to channel")


def _validate_channel_access(client: WebClient, channel_id: str) -> None:
    """Validate that bot token can access and is a member of target conversation."""

    if not channel_id or channel_id[0] not in {"C", "G", "D"}:
        raise SlackReportError(f"invalid channel_id format: {channel_id}")

    auth = client.auth_test()
    bot_user_id = str(auth.get("user_id") or "")
    if not bot_user_id:
        raise SlackReportError("auth.test returned no user_id for bot token")

    info = client.conversations_info(channel=channel_id)
    channel = info.get("channel") or {}
    is_member = bool(channel.get("is_member"))
    if not is_member:
        raise SlackReportError(
            f"bot is not in target channel: {channel_id}. invite bot to channel before sending report"
        )


def send_weekly_report_pdf(
    *,
    pdf_bytes: bytes,
    channel: str,
    filename: str,
    title: str,
    comment: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Upload a PDF report to Slack using the Slack SDK."""

    slack_token = (token or os.environ.get("DASHBOARD_SLACK_BOT_TOKEN") or "").strip()
    if not slack_token:
        raise SlackReportError("DASHBOARD_SLACK_BOT_TOKEN is required")
    if not channel.strip():
        raise SlackReportError("Slack channel is required")

    byte_length = len(pdf_bytes)
    if byte_length <= 0:
        raise SlackReportError("pdf_bytes is empty")
    client = WebClient(token=slack_token)
    channel_id = _resolve_channel_id(client, channel)
    _validate_channel_access(client, channel_id)

    try:
        response = client.files_upload_v2(
            channel=channel_id,
            initial_comment=comment or "",
            file=io.BytesIO(pdf_bytes),
            filename=filename,
            title=title,
        )
    except SlackApiError as exc:
        error = exc.response.get("error") if exc.response is not None else str(exc)
        raise SlackReportError(str(error) or "slack file upload failed") from exc

    result = dict(response.data) if hasattr(response, "data") else dict(response)
    result["delivery_mode"] = "native_file_share"
    result["channel_id"] = channel_id
    return result
