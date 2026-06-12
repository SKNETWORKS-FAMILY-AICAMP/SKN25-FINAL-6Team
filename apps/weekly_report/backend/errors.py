"""주간 리포트에서 쓰는 예외 정의."""

from __future__ import annotations


class SlackReportError(RuntimeError):
    """Slack 전송이 거부되거나 업로드에 실패했을 때 발생한다.

    설정 오류(토큰 없음, 채널 없음)와 API 오류(채널 미초대, 파일 오류) 모두 이 예외로 통일한다.
    """
