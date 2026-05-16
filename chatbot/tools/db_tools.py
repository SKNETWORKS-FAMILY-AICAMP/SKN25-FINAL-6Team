from __future__ import annotations

import json
import sys
from pathlib import Path

from langchain_core.tools import tool

ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from config import settings
from data.seed_payload import SEED_OPERATION_LOGS, clone_payload


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _read_response(rows: list[dict]) -> str:
    return _json({"status": "ok", "data": rows, "count": len(rows)})


@tool(parse_docstring=True)
def read_payments(account_id: int) -> str:
    """Read payment records for the given account.

    Args:
        account_id: Game account ID to look up.
    """
    if settings.use_seed_payload:
        logs = clone_payload(SEED_OPERATION_LOGS)
        rows = [p for p in logs["payments"] if p["account_id"] == account_id]
        return _read_response(rows)
    raise NotImplementedError("DB-backed read_payments is not implemented yet.")


@tool(parse_docstring=True)
def read_refunds(payment_id: int) -> str:
    """Read refund records for the given payment.

    Args:
        payment_id: Payment ID to look up refunds for.
    """
    if settings.use_seed_payload:
        logs = clone_payload(SEED_OPERATION_LOGS)
        rows = [r for r in logs["refunds"] if r["payment_id"] == payment_id]
        return _read_response(rows)
    raise NotImplementedError("DB-backed read_refunds is not implemented yet.")


@tool(parse_docstring=True)
def read_item_delivery_logs(account_id: int) -> str:
    """Read item delivery log records for the given account.

    Args:
        account_id: Game account ID to look up delivery logs for.
    """
    if settings.use_seed_payload:
        logs = clone_payload(SEED_OPERATION_LOGS)
        rows = [d for d in logs["item_delivery_logs"] if d["account_id"] == account_id]
        return _read_response(rows)
    raise NotImplementedError("DB-backed read_item_delivery_logs is not implemented yet.")


@tool(parse_docstring=True)
def read_gacha_logs(account_id: int) -> str:
    """Read gacha pull log records for the given account.

    Args:
        account_id: Game account ID to look up gacha logs for.
    """
    if settings.use_seed_payload:
        logs = clone_payload(SEED_OPERATION_LOGS)
        rows = [g for g in logs["gacha_logs"] if g.get("account_id") == account_id]
        return _read_response(rows)
    raise NotImplementedError("DB-backed read_gacha_logs is not implemented yet.")


@tool(parse_docstring=True)
def write_qa_ticket(payload: dict) -> str:
    """Write a new QA ticket record.

    Args:
        payload: Ticket fields to persist.
    """
    if settings.use_seed_payload:
        return _json({"status": "ok", "ticket_id": payload.get("ticket_id", 1001)})
    raise NotImplementedError("DB-backed write_qa_ticket is not implemented yet.")


@tool(parse_docstring=True)
def write_ticket_analysis(payload: dict) -> str:
    """Write ticket analysis result.

    Args:
        payload: Analysis fields including ticket_id and category.
    """
    if settings.use_seed_payload:
        return _json({"status": "ok", "ticket_id": payload.get("ticket_id")})
    raise NotImplementedError("DB-backed write_ticket_analysis is not implemented yet.")


@tool(parse_docstring=True)
def write_answer_draft(payload: dict) -> str:
    """Write an answer draft for a ticket.

    Args:
        payload: Draft fields including ticket_id and content.
    """
    if settings.use_seed_payload:
        draft_id = 5000 + (payload.get("ticket_id") or 0)
        return _json({"status": "ok", "draft_id": draft_id, "ticket_id": payload.get("ticket_id")})
    raise NotImplementedError("DB-backed write_answer_draft is not implemented yet.")


@tool(parse_docstring=True)
def write_evidence_docs(payload: dict) -> str:
    """Write evidence document references tied to an answer draft.

    Args:
        payload: Evidence fields including draft_id and source description.
    """
    if settings.use_seed_payload:
        return _json({"status": "ok", "draft_id": payload.get("draft_id")})
    raise NotImplementedError("DB-backed write_evidence_docs is not implemented yet.")


@tool(parse_docstring=True)
def write_safety_results(payload: dict) -> str:
    """Write safety evaluation results for an answer draft.

    Args:
        payload: Safety fields including draft_id, ticket_id, hallucination_score,
            toxicity_score, policy_violation_score, factuality_score,
            decision_type, and reason.
    """
    if settings.use_seed_payload:
        return _json({
            "status": "ok",
            "draft_id": payload.get("draft_id"),
            "decision_type": payload.get("decision_type"),
        })
    raise NotImplementedError("DB-backed write_safety_results is not implemented yet.")


@tool(parse_docstring=True)
def append_qa_ticket_message(payload: dict) -> str:
    """Append a user or assistant message to QA_ticket.raw_content.

    Args:
        payload: Message fields including ticket_id, role, and content.
    """
    if settings.use_seed_payload:
        return _json({
            "status": "ok",
            "ticket_id": payload.get("ticket_id"),
            "role": payload.get("role"),
            "appended": True,
        })
    raise NotImplementedError("DB-backed append_qa_ticket_message is not implemented yet.")


@tool(parse_docstring=True)
def write_failed_query(payload: dict) -> str:
    """Write a failed FAQ or low-evidence query for later analysis.

    Args:
        payload: Failed query fields including ticket_id, query, category, and reason.
    """
    if settings.use_seed_payload:
        return _json({
            "status": "ok",
            "ticket_id": payload.get("ticket_id"),
            "query": payload.get("query"),
            "category": payload.get("category"),
            "reason": payload.get("reason"),
        })
    raise NotImplementedError("DB-backed write_failed_query is not implemented yet.")


@tool(parse_docstring=True)
def write_voc_feedback(payload: dict) -> str:
    """Write a VOC feedback record for analysis and follow-up.

    Args:
        payload: VOC fields including ticket_id, user_id, account_id, voc_type,
            sentiment, raw_content, and summary.
    """
    if settings.use_seed_payload:
        return _json({
            "status": "ok",
            "ticket_id": payload.get("ticket_id"),
            "voc_type": payload.get("voc_type"),
            "stored": True,
        })
    raise NotImplementedError("DB-backed write_voc_feedback is not implemented yet.")
