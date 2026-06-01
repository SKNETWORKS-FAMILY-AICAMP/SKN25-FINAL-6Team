from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.service.chatbot_service import run_chatbot


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "expected_category",
        "actual_category",
        "routing_correct",
        "latency_seconds",
        "routing_target",
        "reasoning_node",
        "safety_action",
        "account_id",
        "user_input",
        "response",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _account_id(row: dict[str, Any], default: int | None) -> int | None:
    if row.get("account_id") is not None:
        return int(row["account_id"])
    ground_truth = row.get("db_ground_truth") or {}
    if isinstance(ground_truth, dict) and ground_truth.get("account_id") is not None:
        return int(ground_truth["account_id"])
    return default


def _canonical_category(category: Any) -> str:
    return str(category or "").replace("/", "")


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(row["latency_seconds"]) for row in rows if row.get("latency_seconds") is not None]
    summary: dict[str, Any] = {
        "total_count": len(rows),
        "routing_accuracy": (
            sum(
                1
                for row in rows
                if _canonical_category(row.get("actual_category"))
                == _canonical_category(row.get("expected_category"))
            )
            / len(rows)
            if rows
            else None
        ),
        "latency": _latency_stats(latencies),
        "by_expected_category": {},
    }

    categories = sorted({str(row.get("expected_category") or "") for row in rows})
    for category in categories:
        category_rows = [row for row in rows if row.get("expected_category") == category]
        category_latencies = [
            float(row["latency_seconds"])
            for row in category_rows
            if row.get("latency_seconds") is not None
        ]
        summary["by_expected_category"][category] = {
            "count": len(category_rows),
            "routing_accuracy": (
                sum(
                    1
                    for row in category_rows
                    if _canonical_category(row.get("actual_category"))
                    == _canonical_category(row.get("expected_category"))
                )
                / len(category_rows)
                if category_rows
                else None
            ),
            "latency": _latency_stats(category_latencies),
            "actual_category_counts": _counts(row.get("actual_category") for row in category_rows),
        }
    return summary


def _latency_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "min": None, "max": None, "median": None}
    return {
        "avg": round(sum(values) / len(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "median": round(statistics.median(values), 4),
    }


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def run_eval(
    rows: list[dict[str, Any]],
    *,
    output_path: Path,
    csv_path: Path,
    summary_path: Path,
    limit: int | None,
    start_ticket_id: int,
    default_account_id: int | None,
) -> list[dict[str, Any]]:
    target_rows = rows[:limit] if limit is not None else rows
    completed: list[dict[str, Any]] = []

    for index, row in enumerate(target_rows, start=1):
        question = row.get("user_input") or row.get("question")
        if not question:
            raise ValueError(f"Row {index} is missing user_input/question.")

        ticket_id = start_ticket_id + index - 1
        account_id = _account_id(row, default_account_id)
        expected_category = row.get("expected_category") or row.get("category")
        print(f"[{index}/{len(target_rows)}] ticket={ticket_id} expected={expected_category} account={account_id}")

        started = time.perf_counter()
        try:
            output = run_chatbot(
                ticket_id=ticket_id,
                user_message=question,
                account_id=account_id,
                user_id=1,
                session_id=9100 + index,
                source_type="routing_eval",
            )
            latency = time.perf_counter() - started
            state = output.get("state", {})
            actual_category = state.get("category")
            result = {
                **row,
                "ticket_id": ticket_id,
                "account_id": account_id,
                "expected_category": expected_category,
                "actual_category": actual_category,
                "routing_correct": _canonical_category(actual_category) == _canonical_category(expected_category),
                "latency_seconds": round(latency, 4),
                "routing_target": state.get("routing_target"),
                "reasoning_node": state.get("reasoning_node"),
                "safety_action": state.get("safety_action"),
                "classification_method": state.get("classification_method"),
                "classification_reason": state.get("classification_reason"),
                "retrieval_query": state.get("retrieval_query") or row.get("retrieval_query"),
                "retrieved_documents": state.get("retrieved_documents") or [],
                "faq_failure_reason": state.get("faq_failure_reason"),
                "response": output.get("answer") or "",
            }
            print(
                f"  -> actual={actual_category} latency={latency:.2f}s "
                f"correct={result['routing_correct']}"
            )
        except Exception as exc:
            latency = time.perf_counter() - started
            result = {
                **row,
                "ticket_id": ticket_id,
                "account_id": account_id,
                "expected_category": expected_category,
                "actual_category": None,
                "routing_correct": False,
                "latency_seconds": round(latency, 4),
                "error": repr(exc),
                "response": "",
            }
            print(f"  -> error after {latency:.2f}s: {exc!r}")

        completed.append(result)
        _write_jsonl(output_path, completed)
        _write_csv(csv_path, completed)
        summary_path.write_text(json.dumps(_summarize(completed), ensure_ascii=False, indent=2), encoding="utf-8")

    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run backend routing/latency eval rows through chatbot.")
    parser.add_argument("--input", default="src/chatbot/evals/datasets/routing_category_eval_10_each.jsonl")
    parser.add_argument("--output", default="src/chatbot/evals/experiments/routing_latency_40_results.jsonl")
    parser.add_argument("--csv-output", default="src/chatbot/evals/experiments/routing_latency_40_results.csv")
    parser.add_argument("--summary-output", default="src/chatbot/evals/experiments/routing_latency_40_summary.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start-ticket-id", type=int, default=160000)
    parser.add_argument("--default-account-id", type=int)
    args = parser.parse_args()

    load_dotenv(override=True)
    rows = _load_jsonl(Path(args.input))
    completed = run_eval(
        rows,
        output_path=Path(args.output),
        csv_path=Path(args.csv_output),
        summary_path=Path(args.summary_output),
        limit=args.limit,
        start_ticket_id=args.start_ticket_id,
        default_account_id=args.default_account_id,
    )
    summary = _summarize(completed)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
