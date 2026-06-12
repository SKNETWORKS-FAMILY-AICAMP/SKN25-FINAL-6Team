from __future__ import annotations

from datetime import datetime

from psycopg.rows import dict_row

from agents.answer_agent import (
    AnswerAgent,
    AnswerDraftContext,
    AnswerDraftResult,
)
from common.db.connection import db_connection

from api.services.load_ticket import fetch_ticket_detail


def regenerate_answer_draft(
    ticket_id: int,
    draft_id: int,
    regeneration_reason: str,
    admin_id: int,
) -> dict[str, object]:
    cleaned_reason = str(regeneration_reason or "").strip()
    if not cleaned_reason:
        return {"ok": False, "message": "regeneration_reason is required"}
    try:
        agent = AnswerAgent()

        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        ad.draft_id,
                        COALESCE(sr.retry_count, 0) AS retry_count
                    FROM answer_draft ad
                    LEFT JOIN LATERAL (
                        SELECT sr.retry_count
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

        target = agent.target_repository.fetch(ticket_id)
        evidence_docs = agent.evidence_collector.collect(target)
        context = AnswerDraftContext(
            ticket=target,
            evidence_docs=evidence_docs,
            regeneration_reason=cleaned_reason,
        )
        draft_result = agent.draft_generator.generate(context)
        safety_result = agent.safety_evaluator.evaluate(context, draft_result)
        safety_result = safety_result.model_copy(
            update={"retry_count": int(current_draft.get("retry_count") or 0) + 1}
        )
        final_result = agent.safety_router.route(context, draft_result, safety_result)
        final_result = AnswerDraftResult.model_validate(
            final_result.model_copy(
                update={
                    "metadata": {
                        **final_result.metadata,
                        "regeneration_reason": cleaned_reason,
                        "regenerated_from_draft_id": draft_id,
                    }
                }
            )
        )

        new_draft_id = agent.draft_repository.save_draft(target, final_result)
        agent.draft_repository.save_evidence_docs(new_draft_id, evidence_docs)
        safety_id = agent.draft_repository.save_safety_results(new_draft_id, safety_result)

        with db_connection() as conn:
            with conn.cursor() as cur:
                # admin_event_logs 테이블 사용 중단으로 재생성 이벤트 적재는 비활성화한다.
                # cur.execute(
                #     """
                #     INSERT INTO admin_event_logs (
                #         ticket_id,
                #         node_name,
                #         event_type,
                #         status,
                #         metadata,
                #         actor_admin_id
                #     )
                #     VALUES (%s, %s, %s, %s, %s, %s)
                #     """,
                #     (
                #         ticket_id,
                #         "cs_auto_review_api",
                #         "draft_regenerated",
                #         "success",
                #         Json(
                #             {
                #                 "previous_draft_id": draft_id,
                #                 "new_draft_id": new_draft_id,
                #                 "safety_id": safety_id,
                #                 "retry_count": safety_result.retry_count,
                #                 "regeneration_reason": cleaned_reason,
                #                 "regenerated_at": datetime.utcnow().isoformat(),
                #             }
                #         ),
                #         admin_id,
                #     ),
                # )
                pass

        ticket = fetch_ticket_detail(ticket_id)
        if ticket is None:
            return {"ok": False, "message": "ticket_not_found_after_regeneration"}

        return {
            "ok": True,
            "ticket": ticket,
            "draft_id": new_draft_id,
            "safety_id": safety_id,
            "draft_text": final_result.draft_text,
            "safety_label": final_result.safety_label,
            "review_reason": final_result.review_reason,
        }
    except Exception as exc:
        return {"ok": False, "message": f"draft_regeneration_failed: {exc}"}
