"""output/slack.py 단위 테스트.

Slack SDK와 DB 연결을 monkeypatch로 대체해 실제 API 호출 없이 동작을 검증한다.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from errors import SlackReportError
from output import slack as slack_module
from output.slack import send_weekly_report_pdf


# ── 공통 픽스처 ───────────────────────────────────────────────────────────────

# 각 테스트에서 반복 사용하는 최소 유효 인자 상수.
# PDF 바이트는 실제 PDF 헤더로 시작해야 빈값 체크를 통과한다.
DUMMY_PDF = b"%PDF-1.4 fake"
DUMMY_CHANNEL = "#ops"
DUMMY_FILENAME = "weekly_report_7d_2026-06-12.pdf"
DUMMY_TITLE = "운영 주간 보고서 - 2026-06-12"


def _make_slack_client_mock(channel_id: str = "C0123456789") -> MagicMock:
    """성공 경로에서 사용할 Slack WebClient mock을 반환한다.

    send_weekly_report_pdf 내부 호출 순서:
      1. auth_test         → 봇 인증 확인
      2. conversations_list → 채널명(#ops) → ID(C...) 변환
      3. conversations_info → 봇이 채널에 초대되었는지 확인
      4. files_upload_v2   → PDF 업로드
    각 단계에서 반환값이 없으면 다음 단계로 진행하지 못한다.
    """
    client = MagicMock()
    # auth_test
    client.auth_test.return_value = {"user_id": "U0001"}
    # conversations_list — 채널 이름 → ID 변환용
    client.conversations_list.return_value = {
        "channels": [{"name": "ops", "id": channel_id}],
        "response_metadata": {"next_cursor": ""},
    }
    # conversations_info — 봇 멤버십 확인용
    client.conversations_info.return_value = {
        "channel": {"is_member": True}
    }
    # files_upload_v2 — 실제 업로드
    upload_response = MagicMock()
    upload_response.data = {"ok": True, "file": {"id": "F0001"}}
    client.files_upload_v2.return_value = upload_response
    return client


# ── 설정 오류 검증 ─────────────────────────────────────────────────────────────

class TestSendWeeklyReportPdfConfigErrors:
    """설정 오류는 Slack API 호출 이전에 SlackReportError를 발생시켜야 한다.

    API를 호출하기 전에 검증해야 불필요한 네트워크 왕복을 막을 수 있다.
    """

    def test_missing_token_raises(self, monkeypatch):
        # 환경변수도 없고 token 인자도 없으면 즉시 오류
        monkeypatch.delenv("DASHBOARD_SLACK_BOT_TOKEN", raising=False)

        with pytest.raises(SlackReportError, match="DASHBOARD_SLACK_BOT_TOKEN"):
            send_weekly_report_pdf(
                pdf_bytes=DUMMY_PDF,
                channel=DUMMY_CHANNEL,
                filename=DUMMY_FILENAME,
                title=DUMMY_TITLE,
            )

    def test_empty_channel_raises(self, monkeypatch):
        # 공백만 있는 채널명도 미입력으로 간주한다.
        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        with pytest.raises(SlackReportError, match="채널"):
            send_weekly_report_pdf(
                pdf_bytes=DUMMY_PDF,
                channel="   ",
                filename=DUMMY_FILENAME,
                title=DUMMY_TITLE,
            )

    def test_empty_pdf_bytes_raises(self, monkeypatch):
        # 빈 PDF를 전송하면 Slack에서 파일 오류가 나므로 사전에 차단한다.
        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        with pytest.raises(SlackReportError, match="PDF"):
            send_weekly_report_pdf(
                pdf_bytes=b"",
                channel=DUMMY_CHANNEL,
                filename=DUMMY_FILENAME,
                title=DUMMY_TITLE,
            )

    def test_token_argument_overrides_env(self, monkeypatch):
        """token 인자가 환경변수보다 우선 적용되어야 한다.

        DAG에서 Airflow Variable로 토큰을 직접 주입할 때 이 경로를 사용한다.
        """
        monkeypatch.delenv("DASHBOARD_SLACK_BOT_TOKEN", raising=False)

        client_mock = _make_slack_client_mock()
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        result = send_weekly_report_pdf(
            pdf_bytes=DUMMY_PDF,
            channel=DUMMY_CHANNEL,
            filename=DUMMY_FILENAME,
            title=DUMMY_TITLE,
            token="xoxb-direct",
        )
        assert result["delivery_mode"] == "native_file_share"


# ── 성공 경로 ─────────────────────────────────────────────────────────────────

class TestSendWeeklyReportPdfSuccess:
    """정상 경로: 업로드 성공 시 delivery_mode와 channel_id가 포함된 딕셔너리를 반환한다."""

    def test_returns_result_with_delivery_mode_and_channel_id(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        client_mock = _make_slack_client_mock(channel_id="C0123456789")
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        result = send_weekly_report_pdf(
            pdf_bytes=DUMMY_PDF,
            channel=DUMMY_CHANNEL,
            filename=DUMMY_FILENAME,
            title=DUMMY_TITLE,
        )

        assert result["delivery_mode"] == "native_file_share"
        assert result["channel_id"] == "C0123456789"

    def test_files_upload_v2_called_with_correct_args(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        client_mock = _make_slack_client_mock()
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        send_weekly_report_pdf(
            pdf_bytes=DUMMY_PDF,
            channel=DUMMY_CHANNEL,
            filename=DUMMY_FILENAME,
            title=DUMMY_TITLE,
            comment="주간 리포트입니다.",
        )

        _, kwargs = client_mock.files_upload_v2.call_args
        assert kwargs["filename"] == DUMMY_FILENAME
        assert kwargs["title"] == DUMMY_TITLE
        assert kwargs["initial_comment"] == "주간 리포트입니다."

    def test_channel_id_passed_directly_skips_list(self, monkeypatch):
        """C로 시작하는 채널 ID를 직접 주면 conversations_list를 호출하지 않아야 한다."""
        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        client_mock = _make_slack_client_mock(channel_id="C9999999999")
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        send_weekly_report_pdf(
            pdf_bytes=DUMMY_PDF,
            channel="C9999999999",
            filename=DUMMY_FILENAME,
            title=DUMMY_TITLE,
        )

        client_mock.conversations_list.assert_not_called()


# ── 오류 처리 경로 ────────────────────────────────────────────────────────────

class TestSendWeeklyReportPdfErrorHandling:
    """오류 처리: Slack API 오류와 예상치 못한 예외 모두 SlackReportError로 래핑되어야 한다.

    상위 DAG가 SlackReportError 한 가지 타입만 처리하면 되도록 모든 예외를 통일한다.
    """

    def test_slack_api_error_wraps_as_slack_report_error(self, monkeypatch):
        from slack_sdk.errors import SlackApiError

        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        client_mock = _make_slack_client_mock()
        error_response = {"ok": False, "error": "channel_not_found"}
        # conversations_info 단계에서 SlackApiError 발생 → SlackReportError로 래핑
        client_mock.conversations_info.side_effect = SlackApiError(
            message="channel_not_found",
            response=error_response,
        )
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        with pytest.raises(SlackReportError):
            send_weekly_report_pdf(
                pdf_bytes=DUMMY_PDF,
                channel=DUMMY_CHANNEL,
                filename=DUMMY_FILENAME,
                title=DUMMY_TITLE,
            )

    def test_bot_not_in_channel_raises(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        client_mock = _make_slack_client_mock()
        # is_member=False → 봇이 채널에 없음
        client_mock.conversations_info.return_value = {"channel": {"is_member": False}}
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        # 봇을 채널에 초대하라는 메시지가 포함되어야 운영자가 즉시 조치할 수 있다.
        with pytest.raises(SlackReportError, match="초대"):
            send_weekly_report_pdf(
                pdf_bytes=DUMMY_PDF,
                channel=DUMMY_CHANNEL,
                filename=DUMMY_FILENAME,
                title=DUMMY_TITLE,
            )

    def test_channel_not_found_in_list_raises(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        client_mock = _make_slack_client_mock()
        # 채널 목록에 "ops"가 없음
        client_mock.conversations_list.return_value = {
            "channels": [],
            "response_metadata": {"next_cursor": ""},
        }
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        with pytest.raises(SlackReportError, match="찾지 못했습니다"):
            send_weekly_report_pdf(
                pdf_bytes=DUMMY_PDF,
                channel="#nonexistent",
                filename=DUMMY_FILENAME,
                title=DUMMY_TITLE,
            )

    def test_unexpected_exception_wraps_as_slack_report_error(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        client_mock = _make_slack_client_mock()
        # 네트워크 단절 등 SDK가 아닌 OS 레벨 예외도 래핑한다.
        client_mock.files_upload_v2.side_effect = OSError("네트워크 단절")
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        with pytest.raises(SlackReportError, match="알 수 없는 오류"):
            send_weekly_report_pdf(
                pdf_bytes=DUMMY_PDF,
                channel=DUMMY_CHANNEL,
                filename=DUMMY_FILENAME,
                title=DUMMY_TITLE,
            )


# ── 재시도 로직 ───────────────────────────────────────────────────────────────

class TestUploadRetry:
    """업로드 재시도 로직: Slack ratelimited·서버 오류는 재시도하고, 그 외는 즉시 실패한다.

    Slack의 files.upload API는 ratelimited(429) 를 자주 반환한다.
    재시도 가능한 오류 코드: ratelimited, internal_error
    재시도 불가 오류 코드: not_in_channel, channel_not_found 등
    """

    def test_retryable_error_retries_and_succeeds(self, monkeypatch):
        """ratelimited 오류 후 재시도에서 성공하면 결과를 반환해야 한다."""
        from slack_sdk.errors import SlackApiError

        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")
        # sleep을 no-op으로 대체해 테스트 속도를 높인다.
        monkeypatch.setattr(slack_module.time, "sleep", lambda s: None)

        client_mock = _make_slack_client_mock()
        upload_response = MagicMock()
        upload_response.data = {"ok": True}

        # 첫 번째 호출 → ratelimited, 두 번째 → 성공
        ratelimited_error = SlackApiError("ratelimited", response={"ok": False, "error": "ratelimited"})
        client_mock.files_upload_v2.side_effect = [ratelimited_error, upload_response]

        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        result = send_weekly_report_pdf(
            pdf_bytes=DUMMY_PDF,
            channel=DUMMY_CHANNEL,
            filename=DUMMY_FILENAME,
            title=DUMMY_TITLE,
        )
        assert result["delivery_mode"] == "native_file_share"
        assert client_mock.files_upload_v2.call_count == 2

    def test_non_retryable_error_raises_immediately(self, monkeypatch):
        """not_in_channel 같은 비재시도 오류는 즉시 예외를 발생시켜야 한다."""
        from slack_sdk.errors import SlackApiError

        monkeypatch.setenv("DASHBOARD_SLACK_BOT_TOKEN", "xoxb-test")

        client_mock = _make_slack_client_mock()
        not_allowed = SlackApiError("not_in_channel", response={"ok": False, "error": "not_in_channel"})
        client_mock.files_upload_v2.side_effect = not_allowed
        monkeypatch.setattr(slack_module, "WebClient", lambda token: client_mock)

        with pytest.raises(SlackReportError):
            send_weekly_report_pdf(
                pdf_bytes=DUMMY_PDF,
                channel=DUMMY_CHANNEL,
                filename=DUMMY_FILENAME,
                title=DUMMY_TITLE,
            )
        # 재시도 없이 1회만 호출해야 한다.
        assert client_mock.files_upload_v2.call_count == 1
