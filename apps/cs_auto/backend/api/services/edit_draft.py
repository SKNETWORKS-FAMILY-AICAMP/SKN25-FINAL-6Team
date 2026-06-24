from __future__ import annotations

from psycopg.rows import dict_row

from api.services.load_ticket import fetch_ticket_detail
from common.db.connection import db_connection
from common.observability.langfuse import observe_if_enabled
from observability.langfuse import link_cs_auto_trace


@observe_if_enabled(name="cs_auto_update_answer_draft", as_type="chain", tags=["cs-auto", "draft", "persistence"])
def update_answer_draft(
    ticket_id: int,
    draft_id: int,
    edited_text: str,
    admin_id: int,
    edit_reason: str | None = None,
) -> dict[str, object]:
    trace_payload = {"ticket_id": ticket_id, "draft_id": draft_id, "admin_id": admin_id}
    cleaned_text = str(edited_text or "").strip()
    link_cs_auto_trace(
        trace_payload,
        tags=["draft", "persistence"],
        input_payload={
            "ticket_id": ticket_id,
            "draft_id": draft_id,
            "admin_id": admin_id,
            "edit_reason": edit_reason,
            "edited_text_length": len(cleaned_text),
        },
    )
    if not cleaned_text:
        result = {"ok": False, "message": "edited_text is required"}
        link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "persistence"], output_payload=result)
        return result

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT draft_id
                FROM answer_draft
                WHERE draft_id = %s
                  AND ticket_id = %s
                """,
                (draft_id, ticket_id),
            )
            if cur.fetchone() is None:
                result = {"ok": False, "message": "draft_not_found"}
                link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "persistence"], output_payload=result)
                return result

            cur.execute(
                """
                UPDATE answer_draft
                SET draft_text = %s
                WHERE draft_id = %s
                  AND ticket_id = %s
                """,
                (cleaned_text, draft_id, ticket_id),
            )

            cur.execute(
                """
                UPDATE qa_ticket
                SET assignee_admin_id = %s
                WHERE ticket_id = %s
                """,
                (admin_id, ticket_id),
            )

    ticket = fetch_ticket_detail(ticket_id)
    if ticket is None:
        result = {"ok": False, "message": "ticket_not_found_after_update"}
        link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "persistence"], output_payload=result)
        return result
    result = {"ok": True, "ticket": ticket}
    link_cs_auto_trace({**trace_payload, **ticket}, tags=["draft", "persistence"], output_payload={"ok": True})
    return result
