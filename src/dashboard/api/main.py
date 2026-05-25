"""FastAPI endpoints for dashboard summaries and ticket detail."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from src.common.db.connection import db_connection
from src.dashboard.util import clamp_days
from src.dashboard.workflow import run_dashboard_workflow, run_weekly_report_workflow, start_weekly_report_scheduler
from src.dashboard.workflow.weekly_report.slack import SlackReportError


app = FastAPI(title="Dashboard API", version="1.0.0")


class WeeklyReportSendRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=365)
    slack_channel: str | None = None
    slack_comment: str | None = None


class WeeklyReportNowRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=365)
    slack_comment: str | None = None


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _latest_analysis_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                a.analysis_id,
                a.category,
                a.responder_type,
                a.enriched_query,
                a.risk_level,
                a.sentiment,
                a.routing_target,
                a.summary,
                a.analyzed_at
            FROM ticket_analysis a
            WHERE a.ticket_id = t.ticket_id
            ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
            LIMIT 1
        ) latest_analysis ON TRUE
    """


def _latest_draft_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT d.draft_id, d.analysis_id, d.created_at
            FROM answer_draft d
            WHERE d.ticket_id = t.ticket_id
            ORDER BY d.created_at DESC NULLS LAST, d.draft_id DESC
            LIMIT 1
        ) latest_draft ON TRUE
    """


def _latest_response_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT fr.response_id, fr.draft_id, fr.created_at, fr.safety_action
            FROM final_response fr
            WHERE fr.ticket_id = t.ticket_id
            ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
            LIMIT 1
        ) latest_response ON TRUE
    """


def _latest_safety_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT
                s.safety_id,
                s.hallucination_score,
                s.toxicity_score,
                s.policy_violation_score,
                s.factuality_score,
                s.checked_at,
                s.safety_action,
                s.safety_reason,
                s.retry_count
            FROM safety_results s
            WHERE s.draft_id = d.draft_id
            ORDER BY s.checked_at DESC NULLS LAST, s.safety_id DESC
            LIMIT 1
        ) latest_safety ON TRUE
    """


@app.get("/health")
def health() -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - surface health failure to the UI
        raise HTTPException(status_code=503, detail={"status": "error", "database": "down", "error": str(exc)})
    return {"status": "ok", "database": "ok", "checked_at": checked_at}


@app.get("/summary/overview")
def summary_overview(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    return jsonable_encoder(run_dashboard_workflow("overview", days))


@app.get("/summary/risk")
def summary_risk(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    return jsonable_encoder(run_dashboard_workflow("risk", days))


@app.get("/summary/quality")
def summary_quality(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    return jsonable_encoder(run_dashboard_workflow("quality", days))


@app.get("/summary/all")
def summary_all(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    return jsonable_encoder(run_dashboard_workflow("all", days))


@app.get("/reports/weekly")
def weekly_report_preview(days: int = Query(default=7, ge=1, le=365)) -> dict[str, Any]:
    result = run_weekly_report_workflow(days)
    return jsonable_encoder(result["report"])


@app.get("/reports/weekly/pdf")
def weekly_report_pdf(days: int = Query(default=7, ge=1, le=365)) -> Response:
    result = run_weekly_report_workflow(days)
    filename = f"dashboard_weekly_report_{clamp_days(days)}d.pdf"
    return Response(
        content=result["pdf_bytes"] or b"",
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/reports/weekly/slack")
def weekly_report_slack(request: WeeklyReportSendRequest) -> dict[str, Any]:
    try:
        result = run_weekly_report_workflow(
            request.days,
            send_to_slack=True,
            slack_channel=request.slack_channel,
            slack_comment=request.slack_comment,
        )
    except SlackReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"weekly report slack send failed: {exc}")
    return jsonable_encoder(
        {
            "report": result["report"],
            "slack_result": result["slack_result"],
        }
    )


@app.post("/reports/weekly/slack/now")
def weekly_report_slack_now(request: WeeklyReportNowRequest) -> dict[str, Any]:
    default_channel = (os.environ.get("DASHBOARD_WEEKLY_REPORT_CHANNEL") or "").strip()
    if not default_channel:
        raise HTTPException(status_code=400, detail="DASHBOARD_WEEKLY_REPORT_CHANNEL is not configured")
    try:
        result = run_weekly_report_workflow(
            request.days,
            send_to_slack=True,
            slack_channel=default_channel,
            slack_comment=request.slack_comment,
        )
    except SlackReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"weekly report slack send failed: {exc}")
    return jsonable_encoder(
        {
            "channel": default_channel,
            "report": result["report"],
            "slack_result": result["slack_result"],
        }
    )


def _ticket_list_conditions(
    *,
    window_start: datetime,
    status: str | None,
    risk_level: str | None,
    routing_target: str | None,
    source_type: str | None,
) -> tuple[str, list[Any]]:
    clauses = ["t.inquiry_created_at >= %s"]
    params: list[Any] = [window_start]

    if status:
        clauses.append("t.status = %s")
        params.append(status)
    if source_type:
        clauses.append("t.source_type = %s")
        params.append(source_type)
    if risk_level:
        clauses.append("LOWER(COALESCE(latest_analysis.risk_level, '')) = LOWER(%s)")
        params.append(risk_level)
    if routing_target:
        clauses.append("LOWER(COALESCE(latest_analysis.routing_target, '')) = LOWER(%s)")
        params.append(routing_target)

    return " AND ".join(clauses), params


@app.on_event("startup")
def startup_weekly_report_scheduler() -> None:
    scheduler = start_weekly_report_scheduler()
    app.state.weekly_report_scheduler = scheduler


@app.on_event("shutdown")
def shutdown_weekly_report_scheduler() -> None:
    scheduler = getattr(app.state, "weekly_report_scheduler", None)
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        app.state.weekly_report_scheduler = None


@app.get("/tickets")
def list_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    routing_target: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, Any]:
    window_start = datetime.now() - timedelta(days=clamp_days(days))
    where_sql, params = _ticket_list_conditions(
        window_start=window_start,
        status=status,
        risk_level=risk_level,
        routing_target=routing_target,
        source_type=source_type,
    )
    params.append(limit)

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            items = _fetch_all(
                cur,
                f"""
                SELECT
                    t.ticket_id,
                    t.title,
                    t.status,
                    t.source_type,
                    t.inquiry_created_at,
                    u.nickname,
                    latest_analysis.analysis_id AS latest_analysis_id,
                    latest_analysis.category,
                    latest_analysis.risk_level,
                    latest_analysis.sentiment,
                    latest_analysis.routing_target,
                    latest_draft.draft_id AS latest_draft_id,
                    latest_response.response_id AS latest_response_id
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                {_latest_analysis_join_sql()}
                {_latest_draft_join_sql()}
                {_latest_response_join_sql()}
                WHERE {where_sql}
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT %s
                """,
                tuple(params),
            )
    return jsonable_encoder({"items": items, "limit": limit, "count": len(items), "days": clamp_days(days)})


@app.get("/tickets/{ticket_id}")
def get_ticket_detail(ticket_id: int) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            ticket_row = _fetch_one(
                cur,
                """
                SELECT
                    t.ticket_id,
                    t.account_id,
                    t.user_id,
                    t.title,
                    t.raw_query,
                    t.source_type,
                    t.status,
                    t.inquiry_created_at,
                    t.session_id,
                    t.responder_type,
                    u.email,
                    u.nickname,
                    u.user_status,
                    u.last_login_at,
                    a.game_name,
                    a.uid,
                    a.server_region,
                    a.progression_level,
                    a.account_status
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN game_accounts a ON a.account_id = t.account_id
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            if ticket_row is None:
                raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")

            analyses = _fetch_all(
                cur,
                """
                SELECT
                    analysis_id,
                    ticket_id,
                    category,
                    responder_type,
                    enriched_query,
                    risk_level,
                    sentiment,
                    routing_target,
                    summary,
                    analyzed_at
                FROM ticket_analysis
                WHERE ticket_id = %s
                ORDER BY analyzed_at DESC NULLS LAST, analysis_id DESC
                """,
                (ticket_id,),
            )
            drafts = _fetch_all(
                cur,
                """
                SELECT
                    draft_id,
                    ticket_id,
                    analysis_id,
                    draft_text,
                    prompt_version,
                    created_at
                FROM answer_draft
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, draft_id DESC
                """,
                (ticket_id,),
            )
            draft_ids = [draft["draft_id"] for draft in drafts]
            evidence_docs: list[dict[str, Any]] = []
            safety_results: list[dict[str, Any]] = []
            if draft_ids:
                evidence_docs = _fetch_all(
                    cur,
                    """
                    SELECT
                        evidence_id,
                        draft_id,
                        source_type,
                        source_id,
                        evidence_text,
                        relevance_score,
                        retrieval_rank
                    FROM evidence_docs
                    WHERE draft_id = ANY(%s)
                    ORDER BY draft_id DESC, retrieval_rank ASC, evidence_id DESC
                    """,
                    (draft_ids,),
                )
                safety_results = _fetch_all(
                    cur,
                    """
                    SELECT
                        safety_id,
                        draft_id,
                        hallucination_score,
                        toxicity_score,
                        policy_violation_score,
                        factuality_score,
                        checked_at,
                        safety_action,
                        safety_reason,
                        retry_count
                    FROM safety_results
                    WHERE draft_id = ANY(%s)
                    ORDER BY checked_at DESC NULLS LAST, safety_id DESC
                    """,
                    (draft_ids,),
                )
            final_responses = _fetch_all(
                cur,
                """
                SELECT
                    response_id,
                    ticket_id,
                    draft_id,
                    final_text,
                    safety_action,
                    created_at
                FROM final_response
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, response_id DESC
                """,
                (ticket_id,),
            )
            notifications = _fetch_all(
                cur,
                """
                SELECT
                    notification_id,
                    ticket_id,
                    channel,
                    status,
                    message,
                    error_message,
                    error_category,
                    sent_at
                FROM notification_logs
                WHERE ticket_id = %s
                ORDER BY sent_at DESC NULLS LAST, notification_id DESC
                """,
                (ticket_id,),
            )
            voc_feedback = _fetch_all(
                cur,
                """
                SELECT
                    voc_id,
                    ticket_id,
                    user_id,
                    account_id,
                    voc_type,
                    sentiment,
                    raw_content,
                    topic_keywords,
                    created_at
                FROM voc_feedback
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, voc_id DESC
                """,
                (ticket_id,),
            )
            account_id = ticket_row.get("account_id")
            user_id = ticket_row.get("user_id")
            payment_logs = _fetch_all(
                cur,
                """
                SELECT
                    payment_id,
                    account_id,
                    product_name,
                    product_type,
                    amount,
                    currency,
                    payment_method,
                    payment_status,
                    transaction_id,
                    paid_at
                FROM payments
                WHERE account_id = %s
                ORDER BY paid_at DESC NULLS LAST, payment_id DESC
                """,
                (account_id,),
            ) if account_id is not None else []
            refund_logs = _fetch_all(
                cur,
                """
                SELECT
                    r.refund_id,
                    r.payment_id,
                    r.refund_status,
                    r.refund_reason,
                    r.requested_at,
                    r.processed_at
                FROM refunds r
                JOIN payments p ON p.payment_id = r.payment_id
                WHERE p.account_id = %s
                ORDER BY r.requested_at DESC NULLS LAST, r.refund_id DESC
                """,
                (account_id,),
            ) if account_id is not None else []
            item_delivery_logs = _fetch_all(
                cur,
                """
                SELECT
                    delivery_id,
                    payment_id,
                    account_id,
                    source_type,
                    item_name,
                    quantity,
                    delivery_status,
                    expected_at,
                    delivered_at
                FROM item_delivery_logs
                WHERE account_id = %s
                ORDER BY expected_at DESC NULLS LAST, delivery_id DESC
                """,
                (account_id,),
            ) if account_id is not None else []
            gacha_logs = _fetch_all(
                cur,
                """
                SELECT
                    gacha_id,
                    account_id,
                    banner_name,
                    item_name,
                    item_type,
                    rarity,
                    pity_count,
                    pulled_at
                FROM gacha_logs
                WHERE account_id = %s
                ORDER BY pulled_at DESC NULLS LAST, gacha_id DESC
                """,
                (account_id,),
            ) if account_id is not None else []
            admin_event_logs = _fetch_all(
                cur,
                """
                SELECT
                    log_id,
                    ticket_id,
                    session_id,
                    node_name,
                    event_type,
                    category,
                    routing_target,
                    tool_name,
                    status,
                    error_message,
                    error_category,
                    metadata,
                    created_at
                FROM admin_event_logs
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, log_id DESC
                """,
                (ticket_id,),
            )
            failed_queries = _fetch_all(
                cur,
                """
                SELECT
                    failed_query_id,
                    ticket_id,
                    query,
                    category,
                    reason,
                    created_at
                FROM failed_queries
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, failed_query_id DESC
                """,
                (ticket_id,),
            )

    ticket = {
        "ticket_id": ticket_row["ticket_id"],
        "account_id": ticket_row["account_id"],
        "user_id": ticket_row["user_id"],
        "title": ticket_row["title"],
        "raw_query": ticket_row["raw_query"],
        "source_type": ticket_row["source_type"],
        "status": ticket_row["status"],
        "inquiry_created_at": ticket_row["inquiry_created_at"],
        "session_id": ticket_row["session_id"],
        "responder_type": ticket_row["responder_type"],
    }
    account = {
        "email": ticket_row["email"],
        "nickname": ticket_row["nickname"],
        "user_status": ticket_row["user_status"],
        "last_login_at": ticket_row["last_login_at"],
        "game_name": ticket_row["game_name"],
        "uid": ticket_row["uid"],
        "server_region": ticket_row["server_region"],
        "progression_level": ticket_row["progression_level"],
        "account_status": ticket_row["account_status"],
    }

    return jsonable_encoder(
        {
            "ticket": ticket,
            "account": account,
            "analyses": analyses,
            "drafts": drafts,
            "evidence_docs": evidence_docs,
            "safety_results": safety_results,
            "final_responses": final_responses,
            "notifications": notifications,
            "voc_feedback": voc_feedback,
            "operation_logs": {
                "payments": payment_logs,
                "refunds": refund_logs,
                "item_delivery_logs": item_delivery_logs,
                "gacha_logs": gacha_logs,
            },
            "workflow_logs": {
                "admin_event_logs": admin_event_logs,
                "failed_queries": failed_queries,
            },
        }
    )
