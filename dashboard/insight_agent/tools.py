import json
import sys
from pathlib import Path

from langchain_core.tools import tool


ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from config import settings
from data.seed_payload import (
    SEED_ALERT,
    SEED_DASHBOARD_INPUTS,
    SEED_INSIGHT,
    SEED_METRICS,
    clone_payload,
)


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2)


@tool(parse_docstring=True)
def load_operation_outputs(ticket_id: int | None = None) -> str:
    """Load STEP1, STEP2, safety, and final outcome records created by operation.

    Args:
        ticket_id: Optional QA_ticket.ticket_id filter.
    """
    if settings.use_seed_payload:
        return _json(clone_payload(SEED_DASHBOARD_INPUTS))
    raise NotImplementedError("DB-backed load_operation_outputs is not implemented yet.")


@tool(parse_docstring=True)
def aggregate_operation_metrics(window: str = "daily") -> str:
    """Aggregate observability metrics for STEP3.

    Args:
        window: Aggregation window such as daily, weekly, or monthly.
    """
    if settings.use_seed_payload:
        return _json(clone_payload(SEED_METRICS))
    raise NotImplementedError("DB-backed aggregate_operation_metrics is not implemented yet.")


@tool(parse_docstring=True)
def create_insight_record(ticket_id: int, pattern_risk_level: str = "CRITICAL") -> str:
    """Create the insight row from STEP3 analysis.

    Args:
        ticket_id: QA_ticket.ticket_id.
        pattern_risk_level: Pattern-level risk derived from aggregate metrics.
    """
    if settings.use_seed_payload:
        return _json(clone_payload(SEED_INSIGHT))
    raise NotImplementedError("DB-backed create_insight_record is not implemented yet.")


@tool(parse_docstring=True)
def detect_alert_conditions(metric_name: str = "payment_delivery_failure_rate") -> str:
    """Evaluate observability metrics and decide whether to alert operators.

    Args:
        metric_name: Metric to evaluate for Slack or Discord alerting.
    """
    if settings.use_seed_payload:
        return _json(clone_payload(SEED_ALERT))
    raise NotImplementedError("DB-backed detect_alert_conditions is not implemented yet.")
