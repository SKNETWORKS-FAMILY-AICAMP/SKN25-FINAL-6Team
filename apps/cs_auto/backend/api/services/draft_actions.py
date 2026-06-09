from __future__ import annotations

from datetime import datetime

from psycopg.rows import dict_row
from psycopg.types.json import Json

from common.db.connection import db_connection

from api.services.load_ticket import fetch_ticket_detail


def update_answer_draft(
    ticket_id: int,
    draft_id: int,
    edited_text: str,
    admin_id: int,
    edit_reason: str | None = None,
) -> dict[str, object]:
    cleaned_text = str(edited_text or "").strip()
    if not cleaned_text:
        return {"ok": False, "message": "edited_text is required"}

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
                return {"ok": False, "message": "draft_not_found"}

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
                INSERT INTO admin_event_logs (
                    ticket_id,
                    node_name,
                    event_type,
                    status,
                    metadata,
                    actor_admin_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    ticket_id,
                    "cs_auto_review_api",
                    "draft_updated",
                    "success",
                    Json(
                        {
                            "draft_id": draft_id,
                            "edit_reason": str(edit_reason or ""),
                            "edited_text_length": len(cleaned_text),
                            "edited_at": datetime.utcnow().isoformat(),
                        }
                    ),
                    admin_id,
                ),
            )

    ticket = fetch_ticket_detail(ticket_id)
    if ticket is None:
        return {"ok": False, "message": "ticket_not_found_after_update"}
    return {"ok": True, "ticket": ticket}
