from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
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

from chatbot.service.chatbot_service import stream_chatbot


DEFAULT_DATASET = Path(__file__).parent / "datasets" / "gameops-chatbot-regression-v2.json"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "reports"


def load_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=True)
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


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


def run_one(example: dict[str, Any], ticket_id: int) -> dict[str, Any]:
    inputs = example["inputs"]
    started_at = time.perf_counter()
    error = ""
    result: dict[str, Any] = {}
    try:
        result = stream_chatbot(
            ticket_id=ticket_id,
            user_message=str(inputs["user_message"]),
            category=inputs.get("category"),
            user_id=int(inputs.get("user_id") or 1),
            account_id=int(inputs.get("account_id") or 0),
        )
    except Exception as exc:  # noqa: BLE001 - local eval should record and continue.
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = (time.perf_counter() - started_at) * 1000

    state = result.get("state") or {}
    answer = str(result.get("answer") or "")
    retrieved_documents = state.get("retrieved_documents") or []
    safety_reason = str(state.get("safety_reason") or "")

    return {
        "test_id": (example.get("metadata") or {}).get("test_id"),
        "user_message": inputs.get("user_message"),
        "category": inputs.get("category"),
        "latency_ms": round(latency_ms, 2),
        "answer_length": len(answer),
        "route": state.get("reasoning_node"),
        "safety_action": state.get("safety_action"),
        "safety_passed": state.get("safety_passed"),
        "faq_failure_reason": state.get("faq_failure_reason"),
        "retrieved_document_count": len(retrieved_documents),
        "retrieval_query": state.get("retrieval_query"),
        "second_pass_required": "second_pass=simple_rule_pass" not in safety_reason if safety_reason else "",
        "safety_reason": safety_reason,
        "error": error,
        "field_match_threshold": os.environ.get("FAQ_MIN_FIELD_MATCH_SCORE", "0.01"),
        "rrf_threshold": os.environ.get("FAQ_MIN_RRF_SCORE", "0"),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "test_id",
        "user_message",
        "category",
        "latency_ms",
        "answer_length",
        "route",
        "safety_action",
        "safety_passed",
        "faq_failure_reason",
        "retrieved_document_count",
        "retrieval_query",
        "second_pass_required",
        "safety_reason",
        "error",
        "field_match_threshold",
        "rrf_threshold",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]], output_path: Path) -> None:
    total = len(rows)
    errors = [row for row in rows if row["error"]]
    fallback_rows = [row for row in rows if row["faq_failure_reason"]]
    latencies = [float(row["latency_ms"]) for row in rows]
    sorted_latencies = sorted(latencies)
    avg_latency = sum(latencies) / total if total else 0
    p95_latency = sorted_latencies[int((total - 1) * 0.95)] if total else 0
    print(f"rows={total}")
    print(f"errors={len(errors)}")
    print(f"fallbacks={len(fallback_rows)}")
    print(f"avg_latency_ms={avg_latency:.2f}")
    print(f"p95_latency_ms={p95_latency:.2f}")
    print(f"output={output_path}")
    if fallback_rows:
        print("fallback_reasons=" + json.dumps(
            {
                reason: sum(1 for row in fallback_rows if row["faq_failure_reason"] == reason)
                for reason in sorted({row["faq_failure_reason"] for row in fallback_rows})
            },
            ensure_ascii=False,
        ))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local RAG latency checks without LangSmith.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--test-type", default="rag")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ticket-start", type=int, default=970000)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env()
    examples = load_examples(args.dataset, args.test_type)
    if args.limit is not None:
        examples = examples[: args.limit]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or DEFAULT_OUTPUT_DIR / f"local_{args.test_type}_latency_{timestamp}.csv"

    rows = [
        run_one(example, ticket_id=args.ticket_start + index)
        for index, example in enumerate(examples)
    ]
    write_csv(output_path, rows)
    print_summary(rows, output_path)


if __name__ == "__main__":
    main()
