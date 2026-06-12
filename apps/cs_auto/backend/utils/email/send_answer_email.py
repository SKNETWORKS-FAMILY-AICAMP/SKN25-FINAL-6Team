from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

from psycopg.rows import dict_row

from common.db.connection import db_connection


SMTP_SENDER = "skdusrla1025@gmail.com"
SMTP_RECIPIENT = "rosie1025@naver.com"


def send_answer_email(ticket_id: int, admin_id: int | None = None) -> dict[str, object]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    t.ticket_id,
                    t.title,
                    t.raw_query,
                    fr.response_id,
                    fr.final_text
                FROM qa_ticket t
                JOIN LATERAL (
                    SELECT
                        response_id,
                        final_text,
                        created_at
                    FROM final_response
                    WHERE ticket_id = t.ticket_id
                    ORDER BY created_at DESC NULLS LAST, response_id DESC
                    LIMIT 1
                ) fr ON TRUE
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            row = cur.fetchone()

    if row is None:
        return {"ok": False, "message": "final_response_not_found"}

    subject = f"[CS Auto] Ticket #{row['ticket_id']} 답변"
    body = (
        f"문의 제목: {row['title'] or '-'}\n\n"
        f"문의 내용:\n{row['raw_query'] or '-'}\n\n"
        f"최종 답변:\n{row['final_text'] or '-'}\n"
    )

    message = MIMEText(body, _subtype="plain", _charset="utf-8")
    message["Subject"] = subject
    message["From"] = SMTP_SENDER
    message["To"] = SMTP_RECIPIENT

    with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587"))) as server:
        server.starttls()
        server.login(SMTP_SENDER, os.environ["SMTP_APP_PASSWORD"])
        response = server.sendmail(SMTP_SENDER, [SMTP_RECIPIENT], message.as_string())

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO notification_logs (
                    ticket_id,
                    channel,
                    status,
                    message,
                    error_message,
                    error_category
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING notification_id, sent_at
                """,
                (
                    ticket_id,
                    "email",
                    "sent",
                    body,
                    None,
                    None,
                ),
            )
            notification = cur.fetchone()

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "response_id": row["response_id"],
        "recipient": SMTP_RECIPIENT,
        "sender": SMTP_SENDER,
        "message_id": "smtp_sent" if not response else str(response),
        "notification_id": notification["notification_id"] if notification else None,
        "sent_at": notification["sent_at"] if notification else None,
        "admin_id": admin_id,
    }
