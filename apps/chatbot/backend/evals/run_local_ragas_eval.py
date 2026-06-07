from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
COMMON_SRC_DIR = REPO_ROOT / "packages" / "common-python" / "src"
for path in (PROJECT_ROOT, COMMON_SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.evals.run_langsmith_regression_eval import (
    answer_correctness,
    chatbot_target,
    context_precision,
    context_recall,
    faithfulness,
)


DEFAULT_DATASET = Path(__file__).parent / "datasets" / "gameops-chatbot-regression-v2.json"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "reports"

METRICS: dict[str, Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "answer_correctness": answer_correctness,
    "faithfulness": faithfulness,
    "context_precision": context_precision,
    "context_recall": context_recall,
}


def load_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=True)
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
    os.environ.setdefault("FAQ_MIN_FIELD_MATCH_SCORE", "0.01")


def load_examples(path: Path, test_type: str) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    examples = data.get("examples") if isinstance(data, dict) else data
    if not isinstance(examples, list):
        raise ValueError(f"Unsupported dataset shape: {path}")
    return [
        example
        for example in examples
        if (example.get("metadata") or {}).get("test_type") == test_type
        or (example.get("outputs") or {}).get("test_type") == test_type
    ]


def _metric_value(result: dict[str, Any]) -> Any:
    if "score" in result:
        return result["score"]
    return result.get("value")


def run_one(example: dict[str, Any], metrics: list[str], ticket_id: int) -> dict[str, Any]:
    inputs = dict(example["inputs"])
    inputs["ticket_id"] = ticket_id
    reference_outputs = dict(example["outputs"])

    started_at = time.perf_counter()
    error = ""
    outputs: dict[str, Any] = {}
    try:
        outputs = chatbot_target(inputs)
    except Exception as exc:  # noqa: BLE001 - local eval should record and continue.
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = (time.perf_counter() - started_at) * 1000

    row: dict[str, Any] = {
        "test_id": (example.get("metadata") or {}).get("test_id"),
        "user_message": inputs.get("user_message"),
        "latency_ms": round(latency_ms, 2),
        "answer_length": len(str(outputs.get("answer") or "")),
        "route": outputs.get("route"),
        "safety_action": outputs.get("safety_action"),
        "faq_failure_reason": outputs.get("faq_failure_reason"),
        "retrieved_document_count": outputs.get("retrieved_document_count"),
        "field_match_threshold": os.environ.get("FAQ_MIN_FIELD_MATCH_SCORE", "0.01"),
        "error": error,
    }
    if error:
        for metric_name in metrics:
            row[metric_name] = ""
        return row

    for metric_name in metrics:
        metric = METRICS[metric_name]
        try:
            result = metric(inputs, outputs, reference_outputs)
            row[metric_name] = _metric_value(result)
        except Exception as exc:  # noqa: BLE001
            row[metric_name] = f"metric_error:{type(exc).__name__}"
    return row


def write_csv(path: Path, rows: list[dict[str, Any]], metrics: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "test_id",
        "user_message",
        "latency_ms",
        "answer_length",
        "route",
        "safety_action",
        "faq_failure_reason",
        "retrieved_document_count",
        "field_match_threshold",
        *metrics,
        "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]], output_path: Path, metrics: list[str]) -> None:
    print(f"rows={len(rows)}")
    print(f"errors={sum(1 for row in rows if row['error'])}")
    print(f"output={output_path}")
    for metric in metrics:
        values = []
        non_numeric = []
        for row in rows:
            try:
                values.append(float(row[metric]))
            except (TypeError, ValueError):
                if row.get(metric):
                    non_numeric.append(str(row[metric]))
        if values:
            print(f"{metric}_avg={sum(values) / len(values):.4f}")
        if non_numeric:
            print(f"{metric}_non_numeric={json.dumps(non_numeric[:5], ensure_ascii=False)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local RAGAS evaluation without LangSmith upload.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--test-type", default="rag")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--ticket-start", type=int, default=980000)
    parser.add_argument(
        "--metrics",
        nargs="+",
        default=["answer_correctness", "faithfulness"],
        choices=sorted(METRICS),
        help="RAGAS metrics to run. Use fewer metrics to reduce token usage.",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env()
    examples = load_examples(args.dataset, args.test_type)
    if args.limit is not None:
        examples = examples[: args.limit]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or DEFAULT_OUTPUT_DIR / f"local_{args.test_type}_ragas_{timestamp}.csv"

    rows = [
        run_one(example, args.metrics, ticket_id=args.ticket_start + index)
        for index, example in enumerate(examples)
    ]
    write_csv(output_path, rows, args.metrics)
    print_summary(rows, output_path, args.metrics)


if __name__ == "__main__":
    main()
