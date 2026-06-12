"""주간 대시보드 리포트 PDF를 Slack에 업로드하는 전송 헬퍼."""

from __future__ import annotations

import json
import io
import logging
import os
import time
from datetime import datetime
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from common.db.connection import db_connection

from errors import SlackReportError

# Slack API 오류 코드 중 일시적인 것들 — 이 오류는 재시도하면 성공할 가능성이 있다.
# 채널 없음(channel_not_found), 권한 없음(not_in_channel) 등은 재시도해도 해결되지 않으므로 제외한다.
_RETRYABLE_SLACK_ERRORS = {"ratelimited", "server_error", "fatal_error", "request_timeout", "service_unavailable"}

_MAX_UPLOAD_RETRIES = 3
# 지수 백오프 기본 대기 시간(초): 1차=5s, 2차=10s, 3차=20s
_RETRY_BASE_SECONDS = 5

LOGGER = logging.getLogger(__name__)

# admin_event_logs 삽입 시 고정으로 사용하는 컨텍스트 값들
LOGGER_EVENT_NODE = "weekly_report"
LOGGER_EVENT_TYPE = "weekly_report_slack"
LOGGER_EVENT_CATEGORY = "report"
LOGGER_EVENT_ROUTING_TARGET = "slack"
LOGGER_EVENT_TOOL_NAME = "slack_sdk.files_upload_v2"


def _log_weekly_report_slack_event(
    *,
    status: str,
    channel: str,
    channel_id: str | None,
    filename: str,
    title: str,
    byte_length: int,
    comment: str | None,
    error_message: str | None = None,
    error_category: str | None = None,
    slack_response: dict[str, Any] | None = None,
) -> None:
    """Slack 전송 결과를 admin_event_logs에 기록한다. 실패해도 예외를 흡수한다.

    로그 저장 자체가 실패해도 보고서 전송 흐름을 중단하지 않기 위해
    모든 예외를 로거로만 남기고 바깥으로 전파하지 않는다.
    """
    metadata = {
        "channel": channel,
        "channel_id": channel_id,
        "filename": filename,
        "title": title,
        "byte_length": byte_length,
        "comment": comment,
        "slack_response": slack_response or {},
        "logged_at": datetime.now().isoformat(),
    }
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_event_logs (
                        ticket_id, node_name, event_type, category,
                        routing_target, tool_name, status,
                        error_message, error_category, metadata
                    )
                    VALUES (NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s::json)
                    """,
                    (
                        LOGGER_EVENT_NODE,
                        LOGGER_EVENT_TYPE,
                        LOGGER_EVENT_CATEGORY,
                        LOGGER_EVENT_ROUTING_TARGET,
                        LOGGER_EVENT_TOOL_NAME,
                        status,
                        error_message,
                        error_category,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
    except Exception:
        LOGGER.exception("주간 리포트 Slack 로그 저장에 실패했습니다")


def _resolve_channel_id(client: WebClient, channel: str) -> str:
    """채널 이름(#ops) 또는 채널 ID(C0123456789)를 채널 ID로 변환한다.

    Slack API의 채널 ID는 C(공개)/G(비공개)/D(DM) 접두사로 시작하고 영숫자로 구성된다.
    이름이 주어지면 conversations_list를 페이지네이션으로 순회해 ID를 찾는다.
    봇이 초대되어 있지 않은 채널은 목록에 나타나지 않으므로 찾지 못하면 안내 메시지를 포함한 예외를 발생시킨다.
    """
    raw = (channel or "").strip()
    if not raw:
        raise SlackReportError("Slack 채널이 필요합니다")

    # C/G/D로 시작하고 나머지가 영숫자이면 이미 채널 ID 형식이다.
    if raw[0] in {"C", "G", "D"} and raw[1:].isalnum():
        return raw

    # "#ops" → "ops" 로 정규화해 이름 비교에 사용한다.
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

        # next_cursor가 빈 문자열이면 마지막 페이지다.
        cursor = str((response.get("response_metadata") or {}).get("next_cursor") or "")
        if not cursor:
            break

    raise SlackReportError(f"채널을 찾지 못했습니다: {raw}. 채널 ID 형식(C0123456789 등)으로 넣거나 봇을 초대하세요")


def _validate_channel_access(client: WebClient, channel_id: str) -> None:
    """봇이 해당 채널의 멤버인지 확인한다.

    봇이 채널에 없으면 files_upload_v2가 channel_not_found 오류를 반환하므로
    업로드 시도 전에 미리 확인해 명확한 오류 메시지를 제공한다.
    """
    if not channel_id or channel_id[0] not in {"C", "G", "D"}:
        raise SlackReportError(f"채널 ID 형식이 올바르지 않습니다: {channel_id}")

    auth = client.auth_test()
    bot_user_id = str(auth.get("user_id") or "")
    if not bot_user_id:
        raise SlackReportError("봇 토큰에서 user_id를 확인하지 못했습니다")

    info = client.conversations_info(channel=channel_id)
    channel = info.get("channel") or {}
    if not bool(channel.get("is_member")):
        raise SlackReportError(
            f"봇이 대상 채널에 포함되어 있지 않습니다: {channel_id}. 전송 전에 봇을 채널에 초대하세요"
        )


def _upload_with_retry(
    client: WebClient,
    channel_id: str,
    pdf_bytes: bytes,
    filename: str,
    title: str,
    comment: str | None,
) -> Any:
    """files_upload_v2를 호출하고 일시적 오류에 한해 지수 백오프로 재시도한다.

    _RETRYABLE_SLACK_ERRORS에 없는 오류(권한 없음, 잘못된 파일 등)는 즉시 재발생시킨다.
    모든 재시도가 소진되면 마지막 예외를 그대로 발생시킨다.
    """
    last_exc: SlackApiError | None = None
    for attempt in range(_MAX_UPLOAD_RETRIES):
        try:
            return client.files_upload_v2(
                channel=channel_id,
                initial_comment=comment or "",
                file=io.BytesIO(pdf_bytes),
                filename=filename,
                title=title,
            )
        except SlackApiError as exc:
            error_code = exc.response.get("error") if exc.response is not None else ""
            if error_code not in _RETRYABLE_SLACK_ERRORS:
                raise  # 재시도해도 의미 없는 오류는 즉시 전파
            last_exc = exc
            if attempt < _MAX_UPLOAD_RETRIES - 1:
                # 5s → 10s → 20s 지수 백오프
                delay = _RETRY_BASE_SECONDS * (2 ** attempt)
                LOGGER.warning(
                    "Slack 업로드 재시도 %d/%d (오류: %s, %d초 대기)",
                    attempt + 1, _MAX_UPLOAD_RETRIES, error_code, delay,
                )
                time.sleep(delay)

    raise last_exc  # type: ignore[misc]


def send_weekly_report_pdf(
    *,
    pdf_bytes: bytes,
    channel: str,
    filename: str,
    title: str,
    comment: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """주간 PDF를 Slack에 업로드하고 전송 결과 dict를 반환한다.

    흐름:
    1. 설정 검증 (토큰, 채널, PDF 바이트)
    2. 채널 이름 → ID 변환
    3. 봇 채널 멤버십 확인
    4. files_upload_v2 호출 (재시도 포함)
    5. 성공/실패 모두 admin_event_logs에 기록

    반환 구조에 delivery_mode와 channel_id를 추가해 호출부가 어떤 방식으로 전송됐는지 알 수 있게 한다.
    """
    # 환경변수 우선, 인자로 직접 전달도 허용 (테스트 용이성).
    slack_token = (token or os.environ.get("DASHBOARD_SLACK_BOT_TOKEN") or "").strip()
    if not slack_token:
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=None,
            filename=filename, title=title, byte_length=len(pdf_bytes),
            comment=comment, error_message="DASHBOARD_SLACK_BOT_TOKEN 설정이 없습니다",
            error_category="config_error",
        )
        raise SlackReportError("DASHBOARD_SLACK_BOT_TOKEN 설정이 없습니다")

    if not channel.strip():
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=None,
            filename=filename, title=title, byte_length=len(pdf_bytes),
            comment=comment, error_message="Slack 채널이 필요합니다",
            error_category="config_error",
        )
        raise SlackReportError("Slack 채널이 필요합니다")

    byte_length = len(pdf_bytes)
    if byte_length <= 0:
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=None,
            filename=filename, title=title, byte_length=byte_length,
            comment=comment, error_message="PDF 내용이 비어 있습니다",
            error_category="config_error",
        )
        raise SlackReportError("PDF 내용이 비어 있습니다")

    # channel_id는 로그 기록을 위해 try 블록 밖에서 초기화한다.
    channel_id: str | None = None
    try:
        client = WebClient(token=slack_token)
        channel_id = _resolve_channel_id(client, channel)
        _validate_channel_access(client, channel_id)
        response = _upload_with_retry(client, channel_id, pdf_bytes, filename, title, comment)

    except SlackApiError as exc:
        error = exc.response.get("error") if exc.response is not None else str(exc)
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=channel_id,
            filename=filename, title=title, byte_length=byte_length,
            comment=comment, error_message=str(error) or "Slack 업로드에 실패했습니다",
            error_category="slack_api_error",
        )
        raise SlackReportError(str(error) or "Slack 업로드에 실패했습니다") from exc

    except SlackReportError as exc:
        # _resolve_channel_id, _validate_channel_access에서 발생한 예외 — 로그 후 재발생.
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=channel_id,
            filename=filename, title=title, byte_length=byte_length,
            comment=comment, error_message=str(exc),
            error_category="slack_report_error",
        )
        raise

    except Exception as exc:  # noqa: BLE001
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=channel_id,
            filename=filename, title=title, byte_length=byte_length,
            comment=comment, error_message=str(exc),
            error_category="unexpected_error",
        )
        raise SlackReportError("Slack 업로드 중 알 수 없는 오류가 발생했습니다") from exc

    # slack_sdk 버전에 따라 response.data 속성이 없을 수 있으므로 방어적으로 처리한다.
    result = dict(response.data) if hasattr(response, "data") else dict(response)
    result["delivery_mode"] = "native_file_share"
    result["channel_id"] = channel_id
    _log_weekly_report_slack_event(
        status="success", channel=channel, channel_id=channel_id,
        filename=filename, title=title, byte_length=byte_length,
        comment=comment, slack_response=result,
    )
    return result
