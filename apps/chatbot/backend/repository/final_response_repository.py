from __future__ import annotations

from typing import Any

from common.db.connection import db_connection

from chatbot.repository.base import safe_write


def _optional_int(value: Any) -> int | None:
    # draft_id처럼 비어 있을 수 있는 값을 DB 저장 가능한 int/None으로 정리한다.
    if value in (None, ""):
        return None
    return int(value)


def _final_response_id_is_generated(cur) -> bool:
    # 환경마다 migration 적용 상태가 달라서 response_id 자동 생성 여부를 런타임에 확인한다.
    cur.execute(
        """
        SELECT column_default, is_identity
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'final_response'
          AND column_name = 'response_id'
        """
    )
    row = cur.fetchone()
    if row is None:
        return False
    column_default, is_identity = row
    return bool(column_default) or is_identity == "YES"


def save_final_response(payload: dict[str, Any]) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                if _final_response_id_is_generated(cur):
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
                            _optional_int(payload["ticket_id"]),
                            _optional_int(payload.get("draft_id")),
                            payload["final_text"],
                            payload.get("safety_action"),
                        ),
                    )
                else:
                    # 오래된 DB에서는 response_id 기본값이 없을 수 있어 직접 다음 ID를 채운다.
                    cur.execute("SELECT COALESCE(MAX(response_id), 0) + 1 FROM final_response")
                    response_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO final_response (
                            response_id,
                            ticket_id,
                            draft_id,
                            final_text,
                            safety_action,
                            created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        RETURNING response_id
                        """,
                        (
                            response_id,
                            _optional_int(payload["ticket_id"]),
                            _optional_int(payload.get("draft_id")),
                            payload["final_text"],
                            payload.get("safety_action"),
                        ),
                    )
                row = cur.fetchone()
                saved_response_id = row[0] if row else None

        return {
            "status": "ok",
            "stored": True,
            "response_id": saved_response_id,
            "ticket_id": payload["ticket_id"],
            "draft_id": payload.get("draft_id"),
        }

    return safe_write(operation="write_final_response", payload=payload, writer=_write)
