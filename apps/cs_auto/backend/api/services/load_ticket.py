from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from common.db.connection import db_connection
from common.observability.langfuse import observe_if_enabled
from observability.langfuse import link_cs_auto_trace


@observe_if_enabled(name="cs_auto_get_review_tickets", as_type="chain", tags=["cs-auto", "tickets"])
def get_review_tickets(
    limit: int | None = None,
    status: str | None = None,
    assignee_admin_id: int | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    page: int | None = None,
) -> dict[str, object]:
    trace_payload = {
        "admin_id": assignee_admin_id,
        "status": status,
        "category": category,
        "risk_level": risk_level,
    }
    link_cs_auto_trace(
        trace_payload,
        tags=["tickets"],
        input_payload={
            "limit": limit,
            "status": status,
            "assignee_admin_id": assignee_admin_id,
            "category": category,
            "risk_level": risk_level,
            "page": page,
        },
    )
    tickets = fetch_tickets(
        limit=limit,
        status=status,
        assignee_admin_id=assignee_admin_id,
        category=category,
        risk_level=risk_level,
        page=page,
    )
    result = {
        "tickets": tickets,
        "count": len(tickets),
        "filters": {
            "limit": limit,
            "status": status,
            "assignee_admin_id": assignee_admin_id,
            "category": category,
            "risk_level": risk_level,
            "page": page,
        },
    }
    link_cs_auto_trace(trace_payload, tags=["tickets"], output_payload={"count": result["count"]})
    return result


@observe_if_enabled(name="cs_auto_get_ticket_detail", as_type="chain", tags=["cs-auto", "tickets"])
def get_ticket_detail(ticket_id: int) -> dict[str, object]:
    trace_payload = {"ticket_id": ticket_id}
    link_cs_auto_trace(trace_payload, tags=["tickets"], input_payload={"ticket_id": ticket_id})
    ticket = fetch_ticket_detail(ticket_id)
    if ticket is None:
        result = {"ticket": None, "evidence": [], "history": [], "safety": []}
        link_cs_auto_trace(trace_payload, tags=["tickets"], output_payload={"has_ticket": False})
        return result

    evidence = fetch_ticket_evidence(ticket.get("draft_id"))
    result = {
        "ticket": ticket,
        "evidence": evidence,
    }
    link_cs_auto_trace(
        {**trace_payload, **ticket},
        tags=["tickets"],
        output_payload={"has_ticket": True, "evidence_count": len(evidence)},
    )
    return result


@observe_if_enabled(name="cs_auto_fetch_tickets", as_type="tool", tags=["cs-auto", "tickets", "db"])
def fetch_tickets(
    limit: int | None = None,
    status: str | None = None,
    assignee_admin_id: int | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    page: int | None = None,
) -> list[dict[str, Any]]:
    trace_payload = {
        "admin_id": assignee_admin_id,
        "status": status,
        "category": category,
        "risk_level": risk_level,
    }
    link_cs_auto_trace(
        trace_payload,
        tags=["tickets", "db"],
        input_payload={
            "limit": limit,
            "status": status,
            "assignee_admin_id": assignee_admin_id,
            "category": category,
            "risk_level": risk_level,
            "page": page,
        },
    )
    page_size = limit or 200
    page_no = page or 1
    offset = max(page_no - 1, 0) * page_size
    where_clauses: list[str] = []
    params: list[Any] = []

    if status:
        where_clauses.append("LOWER(COALESCE(t.status, '')) = LOWER(%s)")
        params.append(status)
    if assignee_admin_id is not None:
        where_clauses.append("t.assignee_admin_id = %s")
        params.append(assignee_admin_id)
    if category:
        where_clauses.append("LOWER(COALESCE(a.category, '')) = LOWER(%s)")
        params.append(category)
    if risk_level:
        where_clauses.append("LOWER(COALESCE(a.risk_level, '')) = LOWER(%s)")
        params.append(risk_level)

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
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
                    t.assignee_admin_id,
                    u.nickname,
                    u.email,
                    au.login_id AS assignee_login_id,
                    au.display_name AS assignee_display_name,
                    a.analysis_id,
                    a.category,
                    a.enriched_query,
                    a.risk_level,
                    a.sentiment,
                    a.routing_target,
                    a.summary,
                    a.analyzed_at,
                    d.draft_id,
                    d.draft_text,
                    d.created_at AS draft_created_at,
                    fr.response_id,
                    fr.final_text,
                    s.retry_count,
                    s.safety_action
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN admin_users au ON au.admin_id = t.assignee_admin_id
                LEFT JOIN LATERAL (
                    SELECT
                        ta.analysis_id,
                        ta.category,
                        ta.enriched_query,
                        ta.risk_level,
                        ta.sentiment,
                        ta.routing_target,
                        ta.summary,
                        ta.analyzed_at
                    FROM ticket_analysis ta
                    WHERE ta.ticket_id = t.ticket_id
                    ORDER BY ta.analyzed_at DESC NULLS LAST, ta.analysis_id DESC
                    LIMIT 1
                ) a ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        ad.draft_id,
                        ad.draft_text,
                        ad.created_at
                    FROM answer_draft ad
                    WHERE ad.ticket_id = t.ticket_id
                    ORDER BY ad.created_at DESC NULLS LAST, ad.draft_id DESC
                    LIMIT 1
                ) d ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        fr.response_id,
                        fr.final_text
                    FROM final_response fr
                    WHERE fr.ticket_id = t.ticket_id
                    ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
                    LIMIT 1
                ) fr ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        sr.retry_count,
                        sr.safety_action
                    FROM safety_results sr
                    WHERE sr.draft_id = d.draft_id
                    ORDER BY sr.checked_at DESC NULLS LAST, sr.safety_id DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE {where_sql}
                ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                LIMIT %s OFFSET %s
                """,
                (*params, page_size, offset),
            )
            rows = [dict(row) for row in cur.fetchall()]
    link_cs_auto_trace(trace_payload, tags=["tickets", "db"], output_payload={"count": len(rows)})
    return rows


@observe_if_enabled(name="cs_auto_fetch_ticket_detail", as_type="tool", tags=["cs-auto", "tickets", "db"])
def fetch_ticket_detail(ticket_id: int) -> dict[str, Any] | None:
    trace_payload = {"ticket_id": ticket_id}
    link_cs_auto_trace(trace_payload, tags=["tickets", "db"], input_payload={"ticket_id": ticket_id})
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    t.ticket_id,
                    t.account_id,
                    t.title,
                    t.raw_query,
                    t.source_type,
                    t.status,
                    t.inquiry_created_at,
                    t.assignee_admin_id,
                    u.nickname,
                    u.email,
                    au.login_id AS assignee_login_id,
                    au.display_name AS assignee_display_name,
                    a.category,
                    a.risk_level,
                    a.routing_target,
                    a.summary,
                    d.draft_id,
                    d.draft_text,
                    d.created_at AS draft_created_at,
                    fr.response_id,
                    fr.final_text,
                    s.retry_count
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN admin_users au ON au.admin_id = t.assignee_admin_id
                LEFT JOIN LATERAL (
                    SELECT
                        ta.category,
                        ta.risk_level,
                        ta.routing_target,
                        ta.summary
                    FROM ticket_analysis ta
                    WHERE ta.ticket_id = t.ticket_id
                    ORDER BY ta.analyzed_at DESC NULLS LAST, ta.analysis_id DESC
                    LIMIT 1
                ) a ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        ad.draft_id,
                        ad.draft_text,
                        ad.created_at
                    FROM answer_draft ad
                    WHERE ad.ticket_id = t.ticket_id
                    ORDER BY ad.created_at DESC NULLS LAST, ad.draft_id DESC
                    LIMIT 1
                ) d ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        fr.response_id,
                        fr.final_text
                    FROM final_response fr
                    WHERE fr.ticket_id = t.ticket_id
                    ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
                    LIMIT 1
                ) fr ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        sr.retry_count
                    FROM safety_results sr
                    WHERE sr.draft_id = d.draft_id
                    ORDER BY sr.checked_at DESC NULLS LAST, sr.safety_id DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
    result = dict(row) if row is not None else None
    link_cs_auto_trace(
        {**trace_payload, **(result or {})},
        tags=["tickets", "db"],
        output_payload={"found": result is not None},
    )
    return result


@observe_if_enabled(name="cs_auto_fetch_ticket_evidence", as_type="tool", tags=["cs-auto", "tickets", "db"])
def fetch_ticket_evidence(draft_id: Any) -> list[dict[str, Any]]:
    trace_payload = {"draft_id": draft_id}
    link_cs_auto_trace(trace_payload, tags=["tickets", "db"], input_payload={"draft_id": draft_id})
    if draft_id is None:
        link_cs_auto_trace(trace_payload, tags=["tickets", "db"], output_payload={"count": 0})
        return []

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    e.source_type,
                    e.source_id,
                    e.evidence_text,
                    e.relevance_score,
                    e.retrieval_rank
                FROM evidence_docs e
                WHERE e.draft_id = %s
                ORDER BY e.retrieval_rank ASC NULLS LAST, e.evidence_id DESC
                """,
                (draft_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
    link_cs_auto_trace(trace_payload, tags=["tickets", "db"], output_payload={"count": len(rows)})
    return rows
