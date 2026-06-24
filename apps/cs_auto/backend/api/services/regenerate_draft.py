from __future__ import annotations

from psycopg.rows import dict_row

from agents.answer_agent import AnswerAgent, AnswerDraftContext, AnswerDraftResult
from api.services.load_ticket import fetch_ticket_detail
from common.db.connection import db_connection
from common.observability.langfuse import observe_if_enabled
from observability.langfuse import link_cs_auto_trace


@observe_if_enabled(name="cs_auto_regenerate_answer_draft", as_type="chain", tags=["cs-auto", "draft", "regeneration"])
def regenerate_answer_draft(
    ticket_id: int,
    draft_id: int,
    regeneration_reason: str,
    admin_id: int,
) -> dict[str, object]:
    trace_payload = {"ticket_id": ticket_id, "draft_id": draft_id, "admin_id": admin_id}
    cleaned_reason = str(regeneration_reason or "").strip()
    link_cs_auto_trace(
        trace_payload,
        tags=["draft", "regeneration"],
        input_payload={
            "ticket_id": ticket_id,
            "draft_id": draft_id,
            "admin_id": admin_id,
            "regeneration_reason": cleaned_reason,
        },
    )
    if not cleaned_reason:
        result = {"ok": False, "message": "regeneration_reason is required"}
        link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "regeneration"], output_payload=result)
        return result
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

                if current_draft is not None:
                    cur.execute(
                        """
                        UPDATE qa_ticket
                        SET assignee_admin_id = %s
                        WHERE ticket_id = %s
                        """,
                        (admin_id, ticket_id),
                    )

        if current_draft is None:
            result = {"ok": False, "message": "draft_not_found"}
            link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "regeneration"], output_payload=result)
            return result

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

        ticket = fetch_ticket_detail(ticket_id)
        if ticket is None:
            result = {"ok": False, "message": "ticket_not_found_after_regeneration"}
            link_cs_auto_trace({**trace_payload, **result}, tags=["draft", "regeneration"], output_payload=result)
            return result

        result = {
            "ok": True,
            "ticket": ticket,
            "draft_id": new_draft_id,
            "safety_id": safety_id,
            "draft_text": final_result.draft_text,
            "safety_label": final_result.safety_label,
            "review_reason": final_result.review_reason,
        }
        link_cs_auto_trace(
            {**trace_payload, **ticket, **result},
            tags=["draft", "regeneration"],
            output_payload={
                "ok": True,
                "draft_id": new_draft_id,
                "safety_id": safety_id,
                "safety_label": final_result.safety_label,
            },
        )
        return result
    except Exception as exc:
        result = {"ok": False, "message": f"draft_regeneration_failed: {exc}"}
        link_cs_auto_trace(
            {**trace_payload, **result},
            tags=["draft", "regeneration"],
            output_payload=result,
            error_type=type(exc).__name__,
        )
        return result
