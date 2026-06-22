"""Resolve the reference timestamp for weekly report windows."""

from __future__ import annotations

from datetime import datetime

from psycopg.rows import dict_row

from common.db.connection import db_connection


def resolve_report_reference_now(fallback_now: datetime) -> datetime:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT MAX(t.inquiry_created_at) AS reference_now
                FROM qa_ticket t
                WHERE EXISTS (
                    SELECT 1
                    FROM ticket_analysis a
                    WHERE a.ticket_id = t.ticket_id
                )
                """
            )
            row = cur.fetchone()

    reference_now = None if row is None else row["reference_now"]
    return reference_now or fallback_now
