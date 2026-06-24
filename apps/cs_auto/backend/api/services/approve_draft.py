from __future__ import annotations

from psycopg.rows import dict_row

from api.services.load_ticket import fetch_ticket_detail
from common.db.connection import db_connection
from common.observability.langfuse import observe_if_enabled
from observability.langfuse import link_cs_auto_trace


RESOLVED_TICKET_STATUS = "resolved"


def _next_integer_id(cur, table_name: str, id_column: str) -> int:
    cur.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS next_id FROM {table_name}")
    row = cur.fetchone()
    if isinstance(row, dict):
        return int(row["next_id"])
    return int(row[0])


@observe_if_enabled(name="cs_auto_approve_answer_draft", as_type="chain", tags=["cs-auto", "draft", "approval"])
def approve_answer_draft(
    ticket_id: int,
    draft_id: int | None,
    final_text: str,
    admin_id: int,
    edit_reason: str | None = None,
) -> dict[str, object]:
    trace_payload = {"ticket_id": ticket_id, "draft_id": draft_id, "admin_id": admin_id}
    cleaned_text = str(final_text or "").strip()
    link_cs_auto_trace(
        trace_payload,
        tags=["draft", "approval"],
        input_payload={
            "ticket_id": ticket_id,
            "draft_id": draft_id,
            "admin_id": admin_id,
            "edit_reason": edit_reason,
            "final_text_length": len(cleaned_text),
        },
    )
    if not cleaned_text:
        result = {"ok": False, "message": "final_text is required"}
        link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "approval"], output_payload=result)
        return result

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            current_draft = None
            resolved_draft_id = draft_id

            if resolved_draft_id is not None:
                cur.execute(
                    """
                    SELECT
                        ad.draft_id,
                        sr.safety_action
                    FROM answer_draft ad
                    LEFT JOIN LATERAL (
                        SELECT sr.safety_action
                        FROM safety_results sr
                        WHERE sr.draft_id = ad.draft_id
                        ORDER BY sr.checked_at DESC NULLS LAST, sr.safety_id DESC
                        LIMIT 1
                    ) sr ON TRUE
                    WHERE ad.draft_id = %s
                      AND ad.ticket_id = %s
                    """,
                    (resolved_draft_id, ticket_id),
                )
                current_draft = cur.fetchone()
                if current_draft is None:
                    result = {"ok": False, "message": "draft_not_found"}
                    link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "approval"], output_payload=result)
                    return result
            else:
                cur.execute(
                    """
                    SELECT source_type
                    FROM qa_ticket
                    WHERE ticket_id = %s
                    """,
                    (ticket_id,),
                )
                ticket_row = cur.fetchone()
                if ticket_row is None:
                    result = {"ok": False, "message": "ticket_not_found"}
                    link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "approval"], output_payload=result)
                    return result
                if str(ticket_row.get("source_type") or "") != "chatbot":
                    result = {"ok": False, "message": "draft_not_found"}
                    link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "approval"], output_payload=result)
                    return result

                cur.execute(
                    """
                    INSERT INTO answer_draft (
                        draft_id,
                        ticket_id,
                        draft_text,
                        created_at
                    )
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING draft_id
                    """,
                    (_next_integer_id(cur, "answer_draft", "draft_id"), ticket_id, cleaned_text),
                )
                created_draft = cur.fetchone()
                if created_draft is None:
                    result = {"ok": False, "message": "draft_create_failed"}
                    link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "approval"], output_payload=result)
                    return result
                resolved_draft_id = created_draft["draft_id"]
                current_draft = {"draft_id": resolved_draft_id, "safety_action": None}

            cur.execute(
                """
                INSERT INTO final_response (
                    ticket_id,
                    draft_id,
                    final_text,
                    safety_action,
                    created_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING response_id
                """,
                (
                    ticket_id,
                    resolved_draft_id,
                    cleaned_text,
                    current_draft.get("safety_action"),
                ),
            )
            response_row = cur.fetchone()

            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s,
                    assignee_admin_id = %s
                WHERE ticket_id = %s
                """,
                (RESOLVED_TICKET_STATUS, admin_id, ticket_id),
            )

    ticket = fetch_ticket_detail(ticket_id)
    if ticket is None:
        result = {"ok": False, "message": "ticket_not_found_after_approval"}
        link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "approval"], output_payload=result)
        return result

    result = {
        "ok": True,
        "ticket": ticket,
        "response_id": response_row["response_id"] if response_row else None,
    }
    link_cs_auto_trace(
        {**trace_payload, **ticket, "response_id": result.get("response_id")},
        tags=["draft", "approval"],
        output_payload={"ok": True, "response_id": result.get("response_id")},
    )
    return result
