from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
for path in (PROJECT_ROOT, REPO_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from service.chatbot_service import run_chatbot
from common.observability.logger import summarize_usage, usage_tracking_context


DATASET_DIR = Path(__file__).parent / "datasets"
OUTPUT_DIR = Path(__file__).parent / "outputs"
DEFAULT_DATASET = DATASET_DIR / "gameops-chatbot-e2e-workflow-22-v1.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "gameops_e2e_workflow_eval_v1.json"

FALLBACK_PHRASES = (
    "답변하기 어렵",
    "확인할 수 없습니다",
    "관련 문서를 찾지 못",
    "근거를 찾지 못",
    "fallback",
)

REVIEW_REQUIRED_PHRASES = (
    "운영팀의 검토",
    "운영팀이 검토",
    "검토가 필요",
    "검토할 수 있도록",
    "요청을 전달",
    "접수되었습니다",
    "접수 완료",
    "담당자가 확인",
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


def infer_action(answer: str, state: dict[str, Any]) -> str:
    if state.get("review_required") is True:
        return "REVIEW_REQUIRED"
    safety_action = state.get("safety_action")
    if safety_action and safety_action != "AUTO_RESPONSE":
        return str(safety_action)
    answer_text = str(answer or "")
    if any(phrase.lower() in answer_text.lower() for phrase in REVIEW_REQUIRED_PHRASES):
        return "REVIEW_REQUIRED"
    if state.get("fallback_reason") or state.get("faq_failure_reason"):
        return "SAFE_FALLBACK"
    if any(phrase.lower() in answer_text.lower() for phrase in FALLBACK_PHRASES):
        return "SAFE_FALLBACK"
    return "AUTO_RESPONSE"


def is_fallback(answer: str, state: dict[str, Any]) -> bool:
    return (
        state.get("safety_action") == "SAFE_FALLBACK"
        or bool(state.get("faq_failure_reason"))
        or any(phrase.lower() in str(answer or "").lower() for phrase in FALLBACK_PHRASES)
    )


def contains_all(answer: str, required: list[str]) -> bool:
    return all(item in answer for item in required)


def contains_none(answer: str, forbidden: list[str]) -> bool:
    return not any(item in answer for item in forbidden)


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, int(len(values) * ratio) - 1))
    return sorted(values)[index]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {}
    latencies = [float(row["latency_ms"]) for row in rows]

    fallback_by_agent: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("actual_routing_target") or "unknown")].append(row)
    for agent, agent_rows in grouped.items():
        fallback_count = sum(bool(row["fallback"]) for row in agent_rows)
        fallback_by_agent[agent] = {
            "total": len(agent_rows),
            "fallback_count": fallback_count,
            "fallback_rate": round(fallback_count / len(agent_rows), 4),
        }

    total_cost = sum(float(row.get("total_cost_usd") or 0.0) for row in rows)
    return {
        "total": total,
        "workflow_success_rate": round(sum(bool(row["workflow_success"]) for row in rows) / total, 4),
        "action_match_rate": round(sum(bool(row["action_match"]) for row in rows) / total, 4),
        "routing_match_rate": round(sum(bool(row["routing_match"]) for row in rows) / total, 4),
        "false_fallback_rate": round(sum(bool(row["false_fallback"]) for row in rows) / total, 4),
        "avg_latency_ms": round(sum(latencies) / total, 2),
        "p50_latency_ms": round(percentile(latencies, 0.50) or 0.0, 2),
        "p95_latency_ms": round(percentile(latencies, 0.95) or 0.0, 2),
        "fallback_by_agent": fallback_by_agent,
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in rows),
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows),
        "successful_requests": sum(int(row.get("successful_requests") or 0) for row in rows),
        "total_cost_usd": round(total_cost, 8),
        "avg_cost_usd_per_case": round(total_cost / total, 8),
        "has_estimated_usage": any(bool(row.get("has_estimated_usage")) for row in rows),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    csv_path = path.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "test_id",
        "category",
        "question",
        "expected_routing_target",
        "actual_routing_target",
        "routing_match",
        "expected_action",
        "actual_action",
        "action_match",
        "fallback",
        "false_fallback",
        "workflow_success",
        "latency_ms",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "successful_requests",
        "total_cost_usd",
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
                    if isinstance(row.get(key), (dict, list))
                    else row.get(key)
                    for key in fieldnames
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the full chatbot workflow end to end.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ticket-id-base", type=int, default=880000)
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
        test_id = metadata.get("test_id") or f"E2E-{index:03d}"
        question = str(inputs.get("user_message") or "")
        expected_action = str(outputs.get("expected_action") or "AUTO_RESPONSE")
        expected_routing_target = str(outputs.get("expected_routing_target") or inputs.get("routing_target") or "")
        expected_fallback = bool(outputs.get("false_fallback_expected"))
        must_contain = list(outputs.get("must_contain") or [])
        must_not_contain = list(outputs.get("must_not_contain") or [])

        started_at = time.perf_counter()
        error = ""
        answer = ""
        state: dict[str, Any] = {}
        usage = {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "successful_requests": 0,
            "total_cost_usd": 0.0,
            "has_estimated_usage": False,
            "components": {},
        }
        try:
            with usage_tracking_context() as tracker:
                result = run_chatbot(
                    ticket_id=args.ticket_id_base + index,
                    user_message=question,
                    category=inputs.get("category"),
                    account_id=inputs.get("account_id"),
                    user_id=int(inputs.get("user_id") or 1),
                    session_id=f"e2e-{args.ticket_id_base + index}",
                    source_type=inputs.get("source_type") or "chatbot_eval",
                    ui_category=inputs.get("ui_category"),
                    sub_category=inputs.get("sub_category"),
                    routing_target=inputs.get("routing_target"),
                    fallback_routing_target=inputs.get("fallback_routing_target"),
                )
                usage = summarize_usage(tracker)
            answer = str(result.get("answer") or "")
            state = result.get("state") or {}
        except Exception as exc:
            error = repr(exc)
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

        actual_routing_target = str(state.get("routing_target") or inputs.get("routing_target") or "")
        actual_action = infer_action(answer, state) if not error else "ERROR"
        fallback = is_fallback(answer, state)
        routing_match = not expected_routing_target or actual_routing_target == expected_routing_target
        action_match = actual_action == expected_action or (
            expected_action == "MASKING"
            and not error
            and contains_none(answer, must_not_contain)
        )
        containment_match = contains_all(answer, must_contain) and contains_none(answer, must_not_contain)
        false_fallback = fallback and not expected_fallback
        workflow_success = (
            not error
            and routing_match
            and action_match
            and containment_match
            and not false_fallback
        )

        row = {
            "test_id": test_id,
            "category": inputs.get("category"),
            "question": question,
            "expected_routing_target": expected_routing_target,
            "actual_routing_target": actual_routing_target,
            "routing_match": routing_match,
            "expected_action": expected_action,
            "actual_action": actual_action,
            "action_match": action_match,
            "fallback": fallback,
            "false_fallback": false_fallback,
            "workflow_success": workflow_success,
            "latency_ms": latency_ms,
            "total_tokens": usage.get("total_tokens", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "successful_requests": usage.get("successful_requests", 0),
            "total_cost_usd": usage.get("total_cost_usd", 0.0),
            "has_estimated_usage": usage.get("has_estimated_usage", False),
            "usage_by_component": usage.get("components", {}),
            "answer": answer,
            "error": error,
        }
        rows.append(row)
        print(
            f"[{index}/{len(examples)}] {test_id} "
            f"success={workflow_success} action={actual_action} route={actual_routing_target} "
            f"latency_ms={latency_ms}"
        )

    summary = summarize(rows)
    output_payload = {
        "dataset": dataset_info.get("dataset_info", dataset_info),
        "summary": summary,
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.output, rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
