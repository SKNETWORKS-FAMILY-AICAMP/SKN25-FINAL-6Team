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

from .errors import SlackReportError

# 재시도 대상 Slack 오류 코드 — 일시적인 서버/네트워크 문제만 재시도한다.
# invalid_auth·channel_not_found 같은 설정 오류는 재시도해도 해결되지 않으므로 즉시 실패한다.
_RETRYABLE_SLACK_ERRORS = {"ratelimited", "server_error", "fatal_error", "request_timeout", "service_unavailable"}

# 업로드 최대 재시도 횟수 및 기본 대기 시간(초).
# 지수 백오프: 1차 5초, 2차 10초, 3차(마지막 시도 후에는 대기 없음) → 최대 15초 추가 대기.
_MAX_UPLOAD_RETRIES = 3
_RETRY_BASE_SECONDS = 5

LOGGER = logging.getLogger(__name__)

# admin_event_logs 삽입 시 사용할 고정 메타데이터 값.
# ticket_id=NULL로 티켓과 무관한 시스템 이벤트임을 명시한다.
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
    """Slack 전송 결과(성공·실패 모두)를 admin_event_logs에 기록한다.

    이 함수 자체가 실패해도 전송 오류를 덮어쓰지 않도록 예외를 내부에서 흡수한다.
    전송 결과는 metadata 컬럼에 JSON으로 저장되므로 나중에 탐색·재발송 판단에 활용할 수 있다.
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
                        ticket_id,
                        node_name,
                        event_type,
                        category,
                        routing_target,
                        tool_name,
                        status,
                        error_message,
                        error_category,
                        metadata
                    )
                    VALUES (
                        NULL,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s::json
                    )
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
        # 로그 저장 실패가 Slack 전송 실패 원인을 가려서는 안 된다.
        LOGGER.exception("주간 리포트 Slack 로그 저장에 실패했습니다")


def _resolve_channel_id(client: WebClient, channel: str) -> str:
    """채널 이름(#이름 또는 이름) 또는 이미 ID 형식이면 그대로 반환한다.

    이름으로 입력된 경우 conversations_list를 페이지네이션하며 탐색한다.
    채널이 많은 워크스페이스에서는 API 호출이 여러 번 발생할 수 있으므로
    운영 환경에서는 채널 ID를 직접 입력하는 것을 권장한다.
    """
    raw = (channel or "").strip()
    if not raw:
        raise SlackReportError("Slack 채널이 필요합니다")

    # C/G/D로 시작하고 나머지가 영숫자이면 이미 채널 ID 형식이다.
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

        # next_cursor가 없으면 마지막 페이지다.
        cursor = str((response.get("response_metadata") or {}).get("next_cursor") or "")
        if not cursor:
            break

    raise SlackReportError(f"채널을 찾지 못했습니다: {raw}. 채널 ID 형식(C0123456789 등)으로 넣거나 봇을 초대하세요")


def _validate_channel_access(client: WebClient, channel_id: str) -> None:
    """봇이 해당 채널의 멤버인지 확인한다.

    멤버가 아니면 files_upload_v2 가 channel_not_found 오류를 반환하므로
    업로드 전에 미리 확인해 오류 원인을 명확히 한다.
    """
    if not channel_id or channel_id[0] not in {"C", "G", "D"}:
        raise SlackReportError(f"채널 ID 형식이 올바르지 않습니다: {channel_id}")

    auth = client.auth_test()
    bot_user_id = str(auth.get("user_id") or "")
    if not bot_user_id:
        raise SlackReportError("봇 토큰에서 user_id를 확인하지 못했습니다")

    info = client.conversations_info(channel=channel_id)
    channel = info.get("channel") or {}
    is_member = bool(channel.get("is_member"))
    if not is_member:
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
    """files_upload_v2를 호출하고, 일시적 오류에 한해 지수 백오프로 재시도한다.

    재시도 대상: _RETRYABLE_SLACK_ERRORS에 정의된 오류 코드 (서버·네트워크 이슈)
    즉시 실패: 그 외 오류 (권한 없음, 잘못된 채널 등 — 재시도해도 해결 불가)

    지수 백오프 대기 시간:
      - 1차 실패 후: 5초
      - 2차 실패 후: 10초
      - 3차 실패 후: 대기 없이 예외 전파
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
                # 설정 오류나 권한 오류는 재시도 불필요 — 즉시 상위로 전파
                raise
            last_exc = exc
            if attempt < _MAX_UPLOAD_RETRIES - 1:
                delay = _RETRY_BASE_SECONDS * (2 ** attempt)
                LOGGER.warning(
                    "Slack 업로드 재시도 %d/%d (오류: %s, %d초 대기)",
                    attempt + 1, _MAX_UPLOAD_RETRIES, error_code, delay,
                )
                time.sleep(delay)

    # 모든 재시도 소진 — 마지막 예외를 상위로 전파
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

    처리 순서:
    1. 토큰·채널·PDF 유효성 사전 확인 (설정 오류는 여기서 차단)
    2. 채널 이름 → 채널 ID 변환
    3. 봇 채널 멤버십 확인
    4. PDF 업로드 (일시적 오류 시 재시도)
    5. 성공/실패 결과를 admin_event_logs에 기록

    모든 실패는 SlackReportError로 변환해 반환한다.
    호출자는 SlackReportError를 400, 그 외를 502로 매핑한다.
    """
    # ── 1. 사전 유효성 확인 ──────────────────────────────────────────
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

    # ── 2~4. 채널 resolve → 멤버십 확인 → 업로드 ────────────────────
    channel_id: str | None = None
    try:
        client = WebClient(token=slack_token)
        channel_id = _resolve_channel_id(client, channel)
        _validate_channel_access(client, channel_id)
        response = _upload_with_retry(client, channel_id, pdf_bytes, filename, title, comment)

    except SlackApiError as exc:
        # Slack SDK가 올린 API 오류 (재시도 소진 후 포함)
        error = exc.response.get("error") if exc.response is not None else str(exc)
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=channel_id,
            filename=filename, title=title, byte_length=byte_length,
            comment=comment, error_message=str(error) or "Slack 업로드에 실패했습니다",
            error_category="slack_api_error",
        )
        raise SlackReportError(str(error) or "Slack 업로드에 실패했습니다") from exc

    except SlackReportError as exc:
        # _resolve_channel_id / _validate_channel_access 에서 발생한 설정 오류
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=channel_id,
            filename=filename, title=title, byte_length=byte_length,
            comment=comment, error_message=str(exc),
            error_category="slack_report_error",
        )
        raise

    except Exception as exc:  # noqa: BLE001
        # 예상치 못한 오류 (네트워크 단절 등)
        _log_weekly_report_slack_event(
            status="failed", channel=channel, channel_id=channel_id,
            filename=filename, title=title, byte_length=byte_length,
            comment=comment, error_message=str(exc),
            error_category="unexpected_error",
        )
        raise SlackReportError("Slack 업로드 중 알 수 없는 오류가 발생했습니다") from exc

    # ── 5. 성공 로그 ─────────────────────────────────────────────────
    result = dict(response.data) if hasattr(response, "data") else dict(response)
    result["delivery_mode"] = "native_file_share"
    result["channel_id"] = channel_id
    _log_weekly_report_slack_event(
        status="success", channel=channel, channel_id=channel_id,
        filename=filename, title=title, byte_length=byte_length,
        comment=comment, slack_response=result,
    )
    return result
