"""FastAPI 진입점 — 주간 운영 리포트 백엔드."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from common.db.connection import db_connection

app = FastAPI(title="Weekly Report API")


@app.get("/health")
def health() -> JSONResponse:
    """DB 연결 상태를 확인한다. docker-compose healthcheck 전용."""
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return JSONResponse({"status": "ok", "db": "connected"})
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "db": "disconnected", "detail": str(exc)},
            status_code=503,
        )


@app.post("/report/trigger")
def trigger_report() -> JSONResponse:
    """주간 리포트를 수동으로 즉시 실행한다.

    Airflow 연동 전 수동 트리거용. Slack 채널은 환경변수 DASHBOARD_WEEKLY_REPORT_CHANNEL에서 읽는다.
    """
    import report as report_module

    channel = os.environ.get("DASHBOARD_WEEKLY_REPORT_CHANNEL", "").strip()
    comment = os.environ.get("DASHBOARD_WEEKLY_REPORT_COMMENT", "").strip() or None
    send_slack = bool(channel)

    try:
        result = report_module.run(
            days=7,
            render_pdf=True,
            send_to_slack=send_slack,
            slack_channel=channel or None,
            slack_comment=comment,
        )
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=500)

    return JSONResponse({
        "status": "ok",
        "pdf_bytes": len(result["pdf_bytes"] or b""),
        "slack_sent": result["slack_result"] is not None,
    })
