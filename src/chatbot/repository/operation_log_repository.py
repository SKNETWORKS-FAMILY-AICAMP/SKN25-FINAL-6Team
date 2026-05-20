from __future__ import annotations

from typing import Any

from config import settings
from data.seed_payload import SEED_OPERATION_LOGS, clone_payload

from chatbot.repository.base import read_response, safe_read


def read_payments_by_account(account_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        if settings.use_seed_payload:
            logs = clone_payload(SEED_OPERATION_LOGS)
            rows = [p for p in logs["payments"] if p["account_id"] == account_id]
            return read_response(rows)
        raise NotImplementedError("DB-backed read_payments is not implemented yet.")

    return safe_read(operation="read_payments", reader=_read)


def read_refunds_by_payment(payment_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        if settings.use_seed_payload:
            logs = clone_payload(SEED_OPERATION_LOGS)
            rows = [r for r in logs["refunds"] if r["payment_id"] == payment_id]
            return read_response(rows)
        raise NotImplementedError("DB-backed read_refunds is not implemented yet.")

    return safe_read(operation="read_refunds", reader=_read)


def read_item_delivery_logs_by_account(account_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        if settings.use_seed_payload:
            logs = clone_payload(SEED_OPERATION_LOGS)
            rows = [d for d in logs["item_delivery_logs"] if d["account_id"] == account_id]
            return read_response(rows)
        raise NotImplementedError("DB-backed read_item_delivery_logs is not implemented yet.")

    return safe_read(operation="read_item_delivery_logs", reader=_read)


def read_gacha_logs_by_account(account_id: int) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        if settings.use_seed_payload:
            logs = clone_payload(SEED_OPERATION_LOGS)
            rows = [g for g in logs["gacha_logs"] if g.get("account_id") == account_id]
            return read_response(rows)
        raise NotImplementedError("DB-backed read_gacha_logs is not implemented yet.")

    return safe_read(operation="read_gacha_logs", reader=_read)
