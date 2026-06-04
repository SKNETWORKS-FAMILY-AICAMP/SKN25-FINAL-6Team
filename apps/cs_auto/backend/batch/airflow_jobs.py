from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from service.batch.operation import run_scheduled_analysis_batch, run_scheduled_naver_cafe_draft_batch


def _coerce_target_date(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(value)


def _summary_payload(summary: Any) -> dict[str, Any]:
    return {
        "job_name": summary.job_name,
        "processed_count": summary.processed_count,
        "failed_count": summary.failed_count,
        "skipped_count": summary.skipped_count,
        "processed_ticket_ids": summary.processed_ticket_ids,
        "failed_ticket_ids": summary.failed_ticket_ids,
        "skipped_ticket_ids": summary.skipped_ticket_ids,
    }


def _default_log_dir() -> Path:
    configured = os.getenv("CS_AUTO_BATCH_LOG_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / "logs" / "operation" / "airflow"


def _write_result_log(*, payload: dict[str, Any], run_label: str) -> str:
    log_dir = _default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{payload['job_name']}-{run_label}-{timestamp}.json"
    target = log_dir / filename
    document = {
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "run_label": run_label,
        **payload,
    }
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def run_ticket_analysis_batch(
    *,
    target_date: str | date | datetime | None = None,
    limit: int = 200,
    run_label: str = "scheduled",
) -> dict[str, Any]:
    summary = run_scheduled_analysis_batch(limit=limit, target_date=_coerce_target_date(target_date))
    payload = _summary_payload(summary)
    payload["result_log_path"] = _write_result_log(payload=payload, run_label=run_label)
    if summary.failed_count:
        raise RuntimeError(f"ticket analysis batch failed for ticket_ids={summary.failed_ticket_ids}")
    return payload


def run_naver_cafe_draft_batch(
    *,
    target_date: str | date | datetime | None = None,
    limit: int = 200,
    run_label: str = "scheduled",
) -> dict[str, Any]:
    summary = run_scheduled_naver_cafe_draft_batch(limit=limit, target_date=_coerce_target_date(target_date))
    payload = _summary_payload(summary)
    payload["result_log_path"] = _write_result_log(payload=payload, run_label=run_label)
    if summary.failed_count:
        raise RuntimeError(f"naver_cafe draft batch failed for ticket_ids={summary.failed_ticket_ids}")
    return payload

