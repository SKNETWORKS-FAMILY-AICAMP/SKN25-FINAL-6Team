"""FastAPI 진입점 — 주간 운영 리포트 백엔드."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from common.db.connection import db_connection
from common.observability.langfuse import configure_langfuse, observe_if_enabled, shutdown_langfuse
from weekly_report_langfuse import link_weekly_report_trace

configure_langfuse("weekly-report", default_tags=["weekly-report", "api"])

app = FastAPI(title="Weekly Report API")


@app.on_event("shutdown")
def _shutdown_langfuse_client() -> None:
    shutdown_langfuse()


@app.get("/health")
@observe_if_enabled(
    name="weekly_report_api_health",
    as_type="generation",
    tags=["weekly-report", "api", "feature:health"],
)
def health() -> JSONResponse:
    """DB 연결 상태를 확인한다. docker-compose healthcheck 전용."""
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        payload = {"status": "ok", "db": "connected"}
        link_weekly_report_trace(
            payload,
            tags=["weekly-report", "api", "feature:health"],
            output_payload=payload,
            status="ok",
        )
        return JSONResponse(payload)
    except Exception as exc:
        payload = {"status": "error", "db": "disconnected", "detail": str(exc)}
        link_weekly_report_trace(
            payload,
            tags=["weekly-report", "api", "feature:health"],
            output_payload=payload,
            status="error",
        )
        return JSONResponse(payload, status_code=503)


@app.post("/report/trigger")
@observe_if_enabled(
    name="weekly_report_api_trigger",
    as_type="chain",
    tags=["weekly-report", "api", "feature:report-trigger"],
)
def trigger_report() -> JSONResponse:
    """주간 리포트를 수동으로 즉시 실행한다.

    Airflow 연동 전 수동 트리거용. Slack 채널은 환경변수 DASHBOARD_WEEKLY_REPORT_CHANNEL에서 읽는다.
    """
    import report as report_module

    channel = os.environ.get("DASHBOARD_WEEKLY_REPORT_CHANNEL", "").strip()
    comment = os.environ.get("DASHBOARD_WEEKLY_REPORT_COMMENT", "").strip() or None
    send_slack = bool(channel)
    link_weekly_report_trace(
        {},
        tags=["weekly-report", "api", "feature:report-trigger"],
        input_payload={"days": 7, "send_to_slack": send_slack, "render_pdf": True},
        days=7,
        send_to_slack=send_slack,
        render_pdf=True,
        channel=channel or None,
    )

    try:
        result = report_module.run(
            days=7,
            render_pdf=True,
            send_to_slack=send_slack,
            slack_channel=channel or None,
            slack_comment=comment,
        )
    except Exception as exc:
        payload = {"status": "error", "detail": str(exc)}
        link_weekly_report_trace(
            payload,
            tags=["weekly-report", "api", "feature:report-trigger"],
            output_payload=payload,
            status="error",
            channel=channel or None,
        )
        return JSONResponse(payload, status_code=500)

    payload = {
        "status": "ok",
        "pdf_bytes": len(result["pdf_bytes"] or b""),
        "slack_sent": result["slack_result"] is not None,
    }
    link_weekly_report_trace(
        payload,
        tags=["weekly-report", "api", "feature:report-trigger"],
        output_payload=payload,
        status="ok",
        channel=channel or None,
        pdf_rendered=bool(result["pdf_bytes"]),
        slack_sent=result["slack_result"] is not None,
    )
    return JSONResponse(payload)
