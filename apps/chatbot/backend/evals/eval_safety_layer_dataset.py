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
for path in (PROJECT_ROOT, REPO_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.safety.safety_layer import safety_layer_node
from common.observability.logger import summarize_usage, usage_tracking_context


DATASET_DIR = Path(__file__).parent / "datasets"
OUTPUT_DIR = Path(__file__).parent / "outputs"
DEFAULT_DATASET = DATASET_DIR / "gameops-chatbot-safety-layer-12-v1.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "gameops_safety_layer_eval_v1.json"


def load_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=True)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ.setdefault("LLM_API_KEY", api_key)
        os.environ.setdefault("OPENAI_API_KEY", api_key)


def load_dataset(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    examples = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(examples, list):
        raise ValueError(f"Unsupported dataset shape: {path}")
    return payload if isinstance(payload, dict) else {}, examples


def make_state(example: dict[str, Any]) -> dict[str, Any]:
    inputs = example.get("inputs") or {}
    user_message = str(inputs.get("user_message") or "")
    category = str(inputs.get("category") or "faq")
    documents = inputs.get("retrieved_documents") or []
    return {
        "messages": [{"role": "user", "content": user_message}],
        "raw_query": user_message,
        "masked_content": inputs.get("masked_content") or user_message,
        "normalized_query": inputs.get("normalized_query") or user_message,
        "input_detected_labels": inputs.get("input_detected_labels") or [],
        "category": category,
        "routing_target": inputs.get("routing_target") or f"{category}_agent",
        "reasoning_node": inputs.get("reasoning_node") or f"{category}_agent",
        "draft_id": inputs.get("draft_id"),
        "ticket_id": inputs.get("ticket_id"),
        "session_id": inputs.get("session_id"),
        "draft_text": inputs.get("draft_text") or "",
        "retrieved_documents": documents,
        "evidence_results": documents,
        "payment_context": inputs.get("payment_context"),
        "review_required": inputs.get("review_required", False),
        "retry_count": int(inputs.get("retry_count") or 0),
    }


def _labels_match(expected: list[str], actual: list[str]) -> bool:
    return set(expected or []) <= set(actual or [])


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {}
    latencies = [float(row["latency_ms"]) for row in rows]
    action_matches = [bool(row["safety_action_match"]) for row in rows]
    masking_rows = [row for row in rows if row["expected_action"] == "MASKING"]
    fallback_rows = [row for row in rows if row["expected_action"] == "SAFE_FALLBACK"]
    review_rows = [row for row in rows if row["expected_action"] == "REVIEW_REQUIRED"]
    auto_rows = [row for row in rows if row["expected_action"] == "AUTO_RESPONSE"]
    block_rows = [row for row in rows if row["expected_action"] == "BLOCK_RESPONSE"]

    def accuracy(subset: list[dict[str, Any]]) -> float | None:
        if not subset:
            return None
        return round(sum(bool(row["safety_action_match"]) for row in subset) / len(subset), 4)

    return {
        "total": total,
        "safety_action_match": round(sum(action_matches) / total, 4),
        "auto_response_accuracy": accuracy(auto_rows),
        "masking_accuracy": accuracy(masking_rows),
        "fallback_accuracy": accuracy(fallback_rows),
        "review_required_accuracy": accuracy(review_rows),
        "block_accuracy": accuracy(block_rows),
        "masking_label_accuracy": round(
            sum(bool(row["masking_labels_match"]) for row in masking_rows) / len(masking_rows),
            4,
        )
        if masking_rows
        else None,
        "error_rate": round(sum(bool(row["error"]) for row in rows) / total, 4),
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
        "category",
        "expected_action",
        "actual_action",
        "safety_action_match",
        "expected_masking_labels",
        "actual_masking_labels",
        "masking_labels_match",
        "safety_passed",
        "review_required",
        "factuality_score",
        "hallucination_score",
        "toxicity_score",
        "policy_violation_score",
        "latency_ms",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "successful_requests",
        "total_cost_usd",
        "has_estimated_usage",
        "usage_by_component",
        "safety_reason",
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
    parser = argparse.ArgumentParser(description="Evaluate safety_layer_node against a JSON dataset.")
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
        expected_masking_labels = list(outputs.get("expected_masking_labels") or [])

        started_at = time.perf_counter()
        try:
            with usage_tracking_context() as usage_tracker:
                result = safety_layer_node(make_state(example))
                token_usage = summarize_usage(usage_tracker)
            error = None
        except Exception as exc:
            result = {}
            token_usage = summarize_usage({})
            error = repr(exc)
        latency_ms = (time.perf_counter() - started_at) * 1000

        actual_action = str(result.get("safety_action") or "ERROR")
        actual_masking_labels = list(result.get("masking_labels") or [])
        action_match = expected_action == actual_action
        masking_labels_match = (
            _labels_match(expected_masking_labels, actual_masking_labels)
            if expected_masking_labels
            else True
        )

        row = {
            "test_id": metadata.get("test_id") or f"SAFE-{index:03d}",
            "question": inputs.get("user_message"),
            "category": inputs.get("category"),
            "expected_action": expected_action,
            "actual_action": actual_action,
            "safety_action_match": action_match,
            "expected_masking_labels": expected_masking_labels,
            "actual_masking_labels": actual_masking_labels,
            "masking_labels_match": masking_labels_match,
            "safety_passed": result.get("safety_passed"),
            "review_required": result.get("review_required"),
            "factuality_score": result.get("factuality_score"),
            "hallucination_score": result.get("hallucination_score"),
            "toxicity_score": result.get("toxicity_score"),
            "policy_violation_score": result.get("policy_violation_score"),
            "latency_ms": round(latency_ms, 2),
            "total_tokens": token_usage.get("total_tokens"),
            "prompt_tokens": token_usage.get("prompt_tokens"),
            "completion_tokens": token_usage.get("completion_tokens"),
            "successful_requests": token_usage.get("successful_requests"),
            "total_cost_usd": token_usage.get("total_cost_usd"),
            "has_estimated_usage": token_usage.get("has_estimated_usage"),
            "usage_by_component": token_usage.get("components"),
            "safety_reason": result.get("safety_reason"),
            "error": error,
        }
        rows.append(row)
        print(
            f"[{index}/{len(examples)}] {row['test_id']} "
            f"expected={expected_action} actual={actual_action} "
            f"match={action_match} latency_ms={row['latency_ms']}"
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
