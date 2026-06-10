from __future__ import annotations

from datetime import datetime

from psycopg.rows import dict_row
from psycopg.types.json import Json

from agents.answer_agent import AnswerAgent
from common.db.connection import db_connection

from api.services.load_ticket import fetch_ticket_detail


# 승인 처리에서 반복 사용하는 문자열을 상수로 모은다.
REVIEW_API_NODE_NAME = "cs_auto_review_api"
DRAFT_APPROVED_EVENT_TYPE = "draft_approved"
SUCCESS_STATUS = "success"
RESOLVED_TICKET_STATUS = "resolved"


def approve_answer_draft(
    ticket_id: int,
    draft_id: int,
    final_text: str,
    admin_id: int,
    edit_reason: str | None = None,
) -> dict[str, object]:
    # 프론트에서 보낸 최종 답변을 정규화한다.
    cleaned_text = str(final_text or "").strip()
    if not cleaned_text:
        return {"ok": False, "message": "final_text is required"}

    # AnswerAgent 저장소를 통해 승인 대상 티켓의 기준 정보를 맞춘다.
    agent = AnswerAgent()

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # 현재 티켓과 연결된 초안이 실제로 존재하는지 먼저 확인한다.
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
                (draft_id, ticket_id),
            )
            current_draft = cur.fetchone()
            if current_draft is None:
                return {"ok": False, "message": "draft_not_found"}

            # 초안 검증이 끝난 뒤 티켓 기준 정보를 조회해 에이전트 흐름과 맞춘다.
            target = agent.target_repository.fetch(ticket_id)

            # 승인된 답변을 final_response에 적재한다.
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
                    target.ticket_id,
                    draft_id,
                    cleaned_text,
                    current_draft.get("safety_action"),
                ),
            )
            response_row = cur.fetchone()

            # 승인 완료된 티켓 상태를 resolved로 전환한다.
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                (RESOLVED_TICKET_STATUS, ticket_id),
            )

            # 운영 이력 조회를 위해 승인 이벤트를 남긴다.
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
                    REVIEW_API_NODE_NAME,
                    DRAFT_APPROVED_EVENT_TYPE,
                    SUCCESS_STATUS,
                    Json(
                        {
                            "draft_id": draft_id,
                            "response_id": response_row["response_id"] if response_row else None,
                            "edit_reason": str(edit_reason or ""),
                            "final_text_length": len(cleaned_text),
                            "approved_at": datetime.utcnow().isoformat(),
                        }
                    ),
                    admin_id,
                ),
            )

    ticket = fetch_ticket_detail(ticket_id)
    if ticket is None:
        return {"ok": False, "message": "ticket_not_found_after_approval"}

    return {
        "ok": True,
        "ticket": ticket,
        "response_id": response_row["response_id"] if response_row else None,
    }
