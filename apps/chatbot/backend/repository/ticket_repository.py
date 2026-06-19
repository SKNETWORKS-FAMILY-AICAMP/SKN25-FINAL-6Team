from __future__ import annotations

from typing import Any

from common.db.connection import db_connection

from chatbot.repository.base import safe_read, safe_write


# user_id/account_id처럼 비어 있을 수 있는 값을 DB 저장 가능한 int/None으로 정리한다.
def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def find_collecting_bug_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "").strip()
    session_base = session_id.rsplit("-", 1)[0] if "-" in session_id else session_id

    def _read() -> dict[str, Any]:
        params: list[Any] = [_optional_int(payload["user_id"])]
        account_clause = "AND t.account_id IS NOT DISTINCT FROM %s"
        if payload.get("account_id") in (None, ""):
            account_clause = "AND t.account_id IS NULL"
        else:
            params.append(_optional_int(payload.get("account_id")))
        params.extend([session_base, session_base, f"{session_base}-%"])

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        t.ticket_id,
                        t.raw_query,
                        t.session_id
                    FROM qa_ticket t
                    WHERE t.user_id = %s
                      {account_clause}
                      AND COALESCE(t.source_type, 'chatbot') = 'chatbot'
                      AND LOWER(COALESCE(t.status, '')) = 'collecting'
                      AND (
                        %s = ''
                        OR t.session_id = %s
                        OR t.session_id LIKE %s
                      )
                      AND (
                        COALESCE(t.raw_query, '') LIKE 'User:%%'
                        OR COALESCE(t.raw_query, '') LIKE '[초기 문의]%%'
                      )
                    ORDER BY t.inquiry_created_at DESC NULLS LAST, t.ticket_id DESC
                    LIMIT 1
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
        if row is None:
            return {"status": "ok", "data": [], "count": 0}
        return {
            "status": "ok",
            "data": [
                {
                    "ticket_id": row[0],
                    "raw_query": row[1],
                    "session_id": row[2],
                }
            ],
            "count": 1,
        }

    return safe_read(operation="read_collecting_bug_ticket", reader=_read)


# 전처리 단계에서 새 문의를 qa_ticket에 저장하고 ticket_id를 반환한다.
def save_qa_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO qa_ticket (
                        ticket_id,
                        user_id,
                        account_id,
                        title,
                        raw_query,
                        source_type,
                        status,
                        inquiry_created_at,
                        session_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                    ON CONFLICT (ticket_id)
                    DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        account_id = EXCLUDED.account_id,
                        title = EXCLUDED.title,
                        raw_query = EXCLUDED.raw_query,
                        source_type = EXCLUDED.source_type,
                        status = EXCLUDED.status,
                        session_id = EXCLUDED.session_id
                    """,
                    (
                        _optional_int(payload["ticket_id"]),
                        _optional_int(payload["user_id"]),
                        _optional_int(payload.get("account_id")),
                        payload.get("title") or "chatbot inquiry",
                        payload["raw_query"],
                        payload.get("source_type") or "chatbot",
                        payload.get("status") or "pending",
                        payload.get("session_id"),
                    ),
                )
        return {
            "status": "ok",
            "stored": True,
            "ticket_id": payload["ticket_id"],
        }

    return safe_write(operation="write_qa_ticket", payload=payload, writer=_write)


# ticket_completion 단계에서 qa_ticket의 처리 상태를 resolved/review 등으로 갱신한다.
def update_qa_ticket_status(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE qa_ticket
                    SET status = %s
                    WHERE ticket_id = %s
                    """,
                    (
                        payload["status"],
                        _optional_int(payload["ticket_id"]),
                    ),
                )
                updated_count = cur.rowcount
        return {
            "status": "ok",
            "stored": True,
            "ticket_id": payload["ticket_id"],
            "ticket_status": payload["status"],
            "updated_count": updated_count,
        }

    return safe_write(operation="update_qa_ticket_status", payload=payload, writer=_write)


def update_qa_ticket_raw_query(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE qa_ticket
                    SET raw_query = %s,
                        status = %s
                    WHERE ticket_id = %s
                    """,
                    (
                        payload["raw_query"],
                        payload.get("status"),
                        _optional_int(payload["ticket_id"]),
                    ),
                )
                updated_count = cur.rowcount
        return {
            "status": "ok",
            "stored": True,
            "ticket_id": payload["ticket_id"],
            "ticket_status": payload.get("status"),
            "updated_count": updated_count,
        }

    return safe_write(operation="update_qa_ticket_raw_query", payload=payload, writer=_write)


def delete_qa_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        ticket_id = _optional_int(payload["ticket_id"])
        with db_connection() as conn:
            with conn.cursor() as cur:
                # Some operational logs intentionally keep ticket_id with NO ACTION
                # FKs, so detach/delete those before removing the non-inquiry ticket.
                cur.execute("UPDATE admin_event_logs SET ticket_id = NULL WHERE ticket_id = %s", (ticket_id,))
                admin_event_count = cur.rowcount
                cur.execute("DELETE FROM notification_logs WHERE ticket_id = %s", (ticket_id,))
                notification_count = cur.rowcount
                cur.execute("DELETE FROM failed_queries WHERE ticket_id = %s", (ticket_id,))
                failed_query_count = cur.rowcount
                cur.execute("DELETE FROM final_response WHERE ticket_id = %s", (ticket_id,))
                final_response_count = cur.rowcount
                cur.execute("DELETE FROM answer_draft WHERE ticket_id = %s", (ticket_id,))
                draft_count = cur.rowcount
                cur.execute("DELETE FROM qa_ticket WHERE ticket_id = %s", (ticket_id,))
                ticket_count = cur.rowcount
        return {
            "status": "ok",
            "deleted": True,
            "ticket_id": payload["ticket_id"],
            "ticket_count": ticket_count,
            "draft_count": draft_count,
            "admin_event_detached_count": admin_event_count,
            "notification_count": notification_count,
            "failed_query_count": failed_query_count,
            "final_response_count": final_response_count,
        }

    return safe_write(operation="delete_qa_ticket", payload=payload, writer=_write)
