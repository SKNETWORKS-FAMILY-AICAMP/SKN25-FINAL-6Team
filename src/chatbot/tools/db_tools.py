from __future__ import annotations

import json

from langchain_core.tools import tool


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@tool(parse_docstring=True)
def read_payments(account_id: int) -> str:
    """Read payment records for the given account.

    Args:
        account_id: Game account ID to look up.
    """
    from chatbot.repository.operation_log_repository import read_payments_by_account

    return _json(read_payments_by_account(account_id))


@tool(parse_docstring=True)
def read_refunds(payment_id: int) -> str:
    """Read refund records for the given payment.

    Args:
        payment_id: Payment ID to look up refunds for.
    """
    from chatbot.repository.operation_log_repository import read_refunds_by_payment

    return _json(read_refunds_by_payment(payment_id))


@tool(parse_docstring=True)
def read_item_delivery_logs(account_id: int) -> str:
    """Read item delivery log records for the given account.

    Args:
        account_id: Game account ID to look up delivery logs for.
    """
    from chatbot.repository.operation_log_repository import read_item_delivery_logs_by_account

    return _json(read_item_delivery_logs_by_account(account_id))


@tool(parse_docstring=True)
def read_gacha_logs(account_id: int) -> str:
    """Read gacha pull log records for the given account.

    Args:
        account_id: Game account ID to look up gacha logs.
    """
    from chatbot.repository.operation_log_repository import read_gacha_logs_by_account

    return _json(read_gacha_logs_by_account(account_id))


@tool(parse_docstring=True)
def write_qa_ticket(payload: dict) -> str:
    """Write a new QA ticket record.

    Args:
        payload: QA_ticket fields including ticket_id, user_id, account_id, session_id, and raw_query.
    """
    from chatbot.repository.ticket_repository import save_qa_ticket

    return _json(save_qa_ticket(payload))


@tool(parse_docstring=True)
def write_ticket_analysis(payload: dict) -> str:
    """Write ticket analysis result.

    Args:
        payload: ticket_analysis fields including ticket_id, category, enriched_query, routing_target, and summary.
    """
    from chatbot.repository.analysis_repository import save_ticket_analysis

    return _json(save_ticket_analysis(payload))


@tool(parse_docstring=True)
def write_answer_draft(payload: dict) -> str:
    """Write an answer draft for a ticket.

    Args:
        payload: answer_draft fields including ticket_id, analysis_id, draft_text, and prompt_version.
    """
    from chatbot.repository.draft_repository import save_answer_draft

    return _json(save_answer_draft(payload))


@tool(parse_docstring=True)
def write_evidence_docs(payload: dict) -> str:
    """Write evidence document references tied to an answer draft.

    Args:
        payload: evidence_docs fields including draft_id, source_type, source_id, evidence_text,
            relevance_score, and retrieval_rank.
    """
    from chatbot.repository.draft_repository import save_evidence_docs

    return _json(save_evidence_docs(payload))


@tool(parse_docstring=True)
def write_safety_results(payload: dict) -> str:
    """Write safety evaluation results for an answer draft.

    Args:
        payload: safety_results fields including draft_id, scores, safety_action, safety_reason,
            and retry_count.
    """
    from chatbot.repository.safety_repository import save_safety_results

    return _json(save_safety_results(payload))


@tool(parse_docstring=True)
def write_final_response(payload: dict) -> str:
    """Write the final customer-facing answer.

    Args:
        payload: Final response fields including ticket_id, draft_id, final_text, and safety_action.
    """
    from chatbot.repository.final_response_repository import save_final_response

    return _json(save_final_response(payload))


@tool(parse_docstring=True)
def write_failed_query(payload: dict) -> str:
    """Write a failed FAQ or low-evidence query for later analysis.

    Args:
        payload: Failed query fields including ticket_id, query, category, and reason.
    """
    from chatbot.repository.failed_query_repository import save_failed_query

    return _json(save_failed_query(payload))


@tool(parse_docstring=True)
def write_voc_feedback(payload: dict) -> str:
    """Write a VOC feedback record for analysis and follow-up.

    Args:
        payload: VOC fields including ticket_id, user_id, account_id, voc_type,
            sentiment, raw_content, and topic_keywords.
    """
    from chatbot.repository.voc_repository import save_voc_feedback

    return _json(save_voc_feedback(payload))
