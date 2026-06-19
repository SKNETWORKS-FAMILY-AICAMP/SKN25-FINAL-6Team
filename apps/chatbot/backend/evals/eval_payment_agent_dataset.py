from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
COMMON_SRC_DIR = REPO_ROOT / "packages" / "common-python" / "src"
for path in (PROJECT_ROOT, COMMON_SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.generation.payment_agent import payment_agent_node
from chatbot.generation.response.fixed_responses import PAYMENT_FALLBACK_RESPONSE, SAFE_FALLBACK_RESPONSE
from common.observability.logger import summarize_usage, usage_tracking_context


DATASET_DIR = Path(__file__).parent / "datasets"
OUTPUT_DIR = Path(__file__).parent / "outputs"
DEFAULT_DATASET = DATASET_DIR / "gameops-chatbot-payment-agent-db-grounded-30-v1.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "gameops_payment_agent_eval_v1.json"

RECORD_ID_KEYS = {
    "payments": "payment_id",
    "refunds": "refund_id",
    "item_delivery_logs": "delivery_id",
    "gacha_logs": "gacha_id",
}

REVIEW_TERMS = (
    "검토",
    "확인 후",
    "운영자",
    "담당자",
    "문의가 접수",
    "검토가 필요",
    "확인이 필요",
    "추가 확인",
    "처리 상태를 확인",
    "operator",
    "review",
    "manual",
)


def load_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=True)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)


def load_dataset(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    examples = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(examples, list):
        raise ValueError(f"Unsupported dataset shape: {path}")
    return payload if isinstance(payload, dict) else {}, examples


def make_state(example: dict[str, Any]) -> dict[str, Any]:
    inputs = example.get("inputs") or {}
    message = str(inputs.get("user_message") or "")
    return {
        "messages": [{"role": "user", "content": message}],
        "raw_query": message,
        "masked_content": message,
        "normalized_query": message,
        "category": inputs.get("category") or "payment",
        "routing_target": inputs.get("routing_target") or "payment_agent",
        "is_actionable": True,
        "user_id": inputs.get("user_id"),
        "account_id": inputs.get("account_id"),
        "retry_count": 0,
        # Intentionally omit ticket_id so eval runs do not write production tickets.
    }


def _context_data(result: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    context = result.get("payment_context") if isinstance(result.get("payment_context"), dict) else {}
    data = context.get("data") if isinstance(context.get("data"), dict) else {}
    return {
        key: [row for row in data.get(key, []) if isinstance(row, dict)]
        for key in RECORD_ID_KEYS
    }


def _record_ids(rows: list[dict[str, Any]], id_key: str) -> set[str]:
    return {str(row.get(id_key)) for row in rows if row.get(id_key) is not None}


def db_lookup_match(
    result: dict[str, Any],
    expected_records: dict[str, list[Any]],
) -> tuple[bool, dict[str, Any]]:
    data = _context_data(result)
    matched: dict[str, list[str]] = {}
    retrieved: dict[str, list[str]] = {}
    missing: dict[str, list[str]] = {}

    for record_type, expected_values in expected_records.items():
        id_key = RECORD_ID_KEYS.get(record_type)
        if not id_key:
            continue
        expected = {str(value) for value in expected_values}
        actual = _record_ids(data.get(record_type, []), id_key)
        matched[record_type] = sorted(expected & actual)
        retrieved[record_type] = sorted(actual)
        missing_values = expected - actual
        if missing_values:
            missing[record_type] = sorted(missing_values)

    expected_total = sum(len(values) for values in expected_records.values())
    matched_total = sum(len(values) for values in matched.values())
    ok = expected_total == matched_total
    return ok, {
        "matched_records": matched,
        "retrieved_records": retrieved,
        "missing_records": missing,
    }


def infer_action(answer: str, result: dict[str, Any]) -> str:
    text = " ".join(answer.split())
    if not text or text in {SAFE_FALLBACK_RESPONSE, PAYMENT_FALLBACK_RESPONSE}:
        return "SAFE_FALLBACK"
    if any(term.lower() in text.lower() for term in REVIEW_TERMS):
        return "REVIEW_REQUIRED"
    return "AUTO_RESPONSE"


def action_from_payment_intent(result: dict[str, Any]) -> str | None:
    payment_intent = result.get("payment_intent") if isinstance(result.get("payment_intent"), dict) else {}
    intent_type = result.get("payment_intent_type") or payment_intent.get("intent_type")
    if intent_type == "ACTION_REQUEST":
        return "REVIEW_REQUIRED"
    if intent_type == "READ_ONLY":
        return "AUTO_RESPONSE"
    return None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {}
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "total": total,
        "db_lookup_accuracy": round(sum(bool(row["db_lookup_accuracy"]) for row in rows) / total, 4),
        "action_match": round(sum(bool(row["action_match"]) for row in rows) / total, 4),
        "false_fallback_rate": round(sum(bool(row["false_fallback"]) for row in rows) / total, 4),
        "avg_latency_ms": round(sum(latencies) / total, 2),
        "p95_latency_ms": round(sorted(latencies)[int(total * 0.95) - 1], 2) if total else None,
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in rows),
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows),
        "successful_requests": sum(int(row.get("successful_requests") or 0) for row in rows),
        "total_cost_usd": round(sum(float(row.get("total_cost_usd") or 0.0) for row in rows), 8),
        "has_estimated_usage": any(bool(row.get("has_estimated_usage")) for row in rows),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    csv_path = path.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "test_id",
        "question",
        "expected_action",
        "actual_action",
        "action_match",
        "db_lookup_accuracy",
        "false_fallback",
        "latency_ms",
        "expected_records",
        "matched_records",
        "missing_records",
        "retrieved_records",
        "payment_intent_type",
        "payment_intent_method",
        "payment_intent_reason",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "successful_requests",
        "total_cost_usd",
        "has_estimated_usage",
        "usage_by_component",
        "answer",
        "error",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row.get(key), ensure_ascii=False)
                    if isinstance(row.get(key), (list, dict))
                    else row.get(key)
                    for key in fieldnames
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate payment agent against a DB-grounded JSON dataset.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    load_env()
    dataset_info, examples = load_dataset(args.dataset)
    if args.limit is not None:
        examples = examples[: args.limit]

    rows: list[dict[str, Any]] = []
    for index, example in enumerate(examples, start=1):
        inputs = example.get("inputs") or {}
        outputs = example.get("outputs") or {}
        metadata = example.get("metadata") or {}
        expected_action = str(outputs.get("expected_action") or "")
        expected_records = dict(outputs.get("expected_records") or {})

        started_at = time.perf_counter()
        try:
            with usage_tracking_context() as usage_tracker:
                result = payment_agent_node(make_state(example))
                token_usage = summarize_usage(usage_tracker)
            error = None
        except Exception as exc:
            result = {"draft_text": "", "payment_context": {"data": {}}}
            token_usage = summarize_usage({})
            error = repr(exc)
        latency_ms = (time.perf_counter() - started_at) * 1000

        answer = str(result.get("draft_text") or "")
        payment_intent = result.get("payment_intent") if isinstance(result.get("payment_intent"), dict) else {}
        actual_action = action_from_payment_intent(result) or infer_action(answer, result)
        db_ok, db_details = db_lookup_match(result, expected_records)
        false_fallback = bool(expected_action != "SAFE_FALLBACK" and actual_action == "SAFE_FALLBACK")
        action_ok = bool(expected_action == actual_action)

        row = {
            "test_id": metadata.get("test_id") or f"PAY-{index:03d}",
            "question": inputs.get("user_message"),
            "expected_action": expected_action,
            "actual_action": actual_action,
            "action_match": action_ok,
            "db_lookup_accuracy": db_ok,
            "false_fallback": false_fallback,
            "latency_ms": round(latency_ms, 2),
            "payment_intent_type": result.get("payment_intent_type") or payment_intent.get("intent_type"),
            "payment_intent_method": payment_intent.get("method"),
            "payment_intent_reason": payment_intent.get("reason"),
            "total_tokens": token_usage.get("total_tokens"),
            "prompt_tokens": token_usage.get("prompt_tokens"),
            "completion_tokens": token_usage.get("completion_tokens"),
            "successful_requests": token_usage.get("successful_requests"),
            "total_cost_usd": token_usage.get("total_cost_usd"),
            "has_estimated_usage": token_usage.get("has_estimated_usage"),
            "usage_by_component": token_usage.get("components"),
            "expected_records": expected_records,
            "answer": answer,
            "error": error,
            **db_details,
        }
        rows.append(row)
        print(
            f"[{index}/{len(examples)}] {row['test_id']} "
            f"db_lookup={row['db_lookup_accuracy']} action_match={row['action_match']} "
            f"actual_action={row['actual_action']} latency_ms={row['latency_ms']}"
        )

    report = {
        "dataset": dataset_info.get("dataset_info") or {},
        "summary": summarize(rows),
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    write_csv(args.output, rows)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
