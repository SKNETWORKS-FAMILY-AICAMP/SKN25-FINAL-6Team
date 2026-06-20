from __future__ import annotations

import argparse
import csv
import json
import os
import re
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

from chatbot.generation.bug_agent import BUG_ACCEPTED_RESPONSE, BUG_REPRODUCTION_FORM_RESPONSE, bug_agent_node
from common.observability.logger import summarize_usage, usage_tracking_context


DATASET_DIR = Path(__file__).parent / "datasets"
OUTPUT_DIR = Path(__file__).parent / "outputs"
DEFAULT_DATASET = DATASET_DIR / "gameops-chatbot-bug-agent-synthetic-20-v1.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "gameops_bug_agent_eval_v1.json"

REVIEW_TERMS = (
    "접수",
    "검토",
    "운영",
    "로그",
    "재현",
    "확인 필요",
    "review",
    "operator",
    "manual",
)

CORE_INFO_SLOTS = {
    "device",
    "os",
    "occurred_at",
    "error_code",
    "error_message",
    "reproduction_steps",
}

SLOT_KEYWORDS = {
    "device": ("기기", "디바이스", "모바일", "PC", "아이폰", "갤럭시", "iPhone", "Android", "iOS"),
    "os": ("OS", "운영체제", "윈도우", "Windows", "Android", "iOS"),
    "occurred_at": ("발생 시점", "발생 시간", "언제", "시점", "시간"),
    "reproduction_steps": ("재현", "반복", "단계", "상황", "어떻게", "진행", "조건"),
    "error_code": ("오류 코드", "에러 코드", "코드"),
    "error_message": ("오류 메시지", "에러 메시지", "메시지", "문구"),
    "quest_name": ("퀘스트", "임무", "미션", "NPC"),
    "location": ("위치", "지역", "장소", "맵", "스테이지"),
    "settings": ("설정", "옵션"),
    "graphics_settings": ("그래픽", "화질", "프레임", "fps", "설정"),
    "screenshot_request": ("스크린샷", "화면", "이미지", "첨부", "캡처"),
    "network_environment": ("네트워크", "와이파이", "Wi-Fi", "LTE", "5G", "통신"),
    "event_name": ("이벤트", "보스"),
    "progress_state": ("진행도", "진행 상태", "단계", "완료"),
    "achievement_name": ("업적", "달성"),
    "controller_model": ("컨트롤러", "패드", "모델"),
    "character_name": ("캐릭터", "캐릭터명"),
    "costume_name": ("의상", "코스튬"),
    "input_method": ("입력", "키보드", "IME", "한글"),
    "link_type": ("링크", "초대"),
    "storage_status": ("저장 공간", "용량", "스토리지"),
    "mail_title": ("우편", "알림", "제목"),
}


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


def make_state(example: dict[str, Any], *, bug_collection_status: str | None = None) -> dict[str, Any]:
    inputs = example.get("inputs") or {}
    message = str(inputs.get("user_message") or "")
    state = {
        "messages": [{"role": "user", "content": message}],
        "raw_query": message,
        "masked_content": message,
        "normalized_query": message,
        "category": inputs.get("category") or "bug",
        "routing_target": inputs.get("routing_target") or "bug_agent",
        "is_actionable": True,
        "user_id": inputs.get("user_id") or 1,
        "account_id": inputs.get("account_id"),
        "retry_count": 0,
        # Intentionally omit ticket_id so eval runs do not write production tickets.
    }
    if bug_collection_status:
        state["bug_collection_status"] = bug_collection_status
        if bug_collection_status == "ready_for_review":
            state["initial_bug_query"] = message
            state["bug_report_form"] = message
    return state


def infer_action(answer: str, result: dict[str, Any]) -> str:
    if result.get("review_required") is True or result.get("safety_action") == "REVIEW_REQUIRED":
        return "REVIEW_REQUIRED"
    text = " ".join(str(answer or "").split())
    if not text:
        return "SAFE_FALLBACK"
    if text in {BUG_REPRODUCTION_FORM_RESPONSE, BUG_ACCEPTED_RESPONSE}:
        return str(result.get("safety_action") or "AUTO_RESPONSE")
    if any(term.lower() in text.lower() for term in REVIEW_TERMS):
        return "REVIEW_REQUIRED"
    return "AUTO_RESPONSE"


def slot_match(answer: str, slot: str) -> bool:
    keywords = SLOT_KEYWORDS.get(slot, (slot,))
    lower_answer = answer.lower()
    if any(keyword.lower() in lower_answer for keyword in keywords):
        return True

    readable_patterns = {
        "device": (r"기기", r"디바이스", r"pc", r"iphone", r"android", r"ios"),
        "os": (r"운영체제", r"\bos\b", r"windows", r"android", r"ios"),
        "occurred_at": (r"발생.*(시점|시간)", r"정확한 시간", r"언제", r"\w+\s*시\b"),
        "reproduction_steps": (r"재현", r"반복", r"특정 상황", r"구체적인 상황", r"어떤 상황", r"지속적으로 발생"),
        "error_code": (r"(오류|에러)\s*(코드\s*)?\d+", r"\bcode\s*\d+"),
        "error_message": (r"오류\s*메시지", r"에러\s*메시지", r"오류.*나타", r"메시지.*나타", r"문구"),
    }
    return any(re.search(pattern, lower_answer, flags=re.IGNORECASE) for pattern in readable_patterns.get(slot, ()))


def required_info_coverage(answer: str, slots: list[str]) -> tuple[float, list[str], list[str]]:
    if not slots:
        return 1.0, [], []
    matched = [slot for slot in slots if slot_match(answer, slot)]
    missing = [slot for slot in slots if slot not in matched]
    return round(len(matched) / len(slots), 4), matched, missing


def expected_slot_groups(outputs: dict[str, Any]) -> tuple[list[str], list[str]]:
    if outputs.get("required_core_info_slots") is not None or outputs.get("optional_info_slots") is not None:
        return (
            list(outputs.get("required_core_info_slots") or []),
            list(outputs.get("optional_info_slots") or []),
        )
    slots = list(outputs.get("required_info_slots") or [])
    core_slots = [slot for slot in slots if slot in CORE_INFO_SLOTS]
    optional_slots = [slot for slot in slots if slot not in CORE_INFO_SLOTS]
    return core_slots, optional_slots


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {}
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "total": total,
        "required_info_coverage": round(
            sum(float(row["required_core_info_coverage"]) for row in rows) / total,
            4,
        ),
        "required_core_info_coverage": round(
            sum(float(row["required_core_info_coverage"]) for row in rows) / total,
            4,
        ),
        "required_core_info_full_match": round(
            sum(bool(row["required_core_info_full_match"]) for row in rows) / total,
            4,
        ),
        "optional_context_info_coverage": round(
            sum(float(row["optional_context_info_coverage"]) for row in rows) / total,
            4,
        ),
        "action_match": round(sum(bool(row["action_match"]) for row in rows) / total, 4),
        "false_fallback_rate": round(sum(bool(row["false_fallback"]) for row in rows) / total, 4),
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
        "expected_action",
        "actual_action",
        "action_match",
        "required_info_coverage",
        "required_core_info_coverage",
        "required_core_info_full_match",
        "expected_core_slots",
        "matched_core_slots",
        "missing_core_slots",
        "optional_context_info_coverage",
        "expected_optional_slots",
        "matched_optional_slots",
        "missing_optional_slots",
        "false_fallback",
        "latency_ms",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "successful_requests",
        "total_cost_usd",
        "has_estimated_usage",
        "usage_by_component",
        "bug_collection_status",
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
    parser = argparse.ArgumentParser(description="Evaluate bug agent against a synthetic bug-report dataset.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--bug-collection-status",
        choices=["collecting", "ready_for_review"],
        default=None,
        help="Optional runtime mode override. Omit it to evaluate the full LLM bug agent path.",
    )
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
        expected_core_slots, expected_optional_slots = expected_slot_groups(outputs)

        started_at = time.perf_counter()
        try:
            with usage_tracking_context() as usage_tracker:
                result = bug_agent_node(make_state(example, bug_collection_status=args.bug_collection_status))
                token_usage = summarize_usage(usage_tracker)
            error = None
        except Exception as exc:
            result = {"draft_text": ""}
            token_usage = summarize_usage({})
            error = repr(exc)
        latency_ms = (time.perf_counter() - started_at) * 1000

        answer = str(result.get("draft_text") or "")
        actual_action = infer_action(answer, result)
        core_coverage, matched_core_slots, missing_core_slots = required_info_coverage(answer, expected_core_slots)
        optional_coverage, matched_optional_slots, missing_optional_slots = required_info_coverage(
            answer,
            expected_optional_slots,
        )
        action_ok = bool(expected_action == actual_action)
        false_fallback = bool(expected_action != "SAFE_FALLBACK" and actual_action == "SAFE_FALLBACK")

        row = {
            "test_id": metadata.get("test_id") or f"BUG-{index:03d}",
            "question": inputs.get("user_message"),
            "expected_action": expected_action,
            "actual_action": actual_action,
            "action_match": action_ok,
            "required_info_coverage": core_coverage,
            "required_core_info_coverage": core_coverage,
            "required_core_info_full_match": core_coverage >= 1.0,
            "expected_core_slots": expected_core_slots,
            "matched_core_slots": matched_core_slots,
            "missing_core_slots": missing_core_slots,
            "optional_context_info_coverage": optional_coverage,
            "expected_optional_slots": expected_optional_slots,
            "matched_optional_slots": matched_optional_slots,
            "missing_optional_slots": missing_optional_slots,
            "false_fallback": false_fallback,
            "latency_ms": round(latency_ms, 2),
            "total_tokens": token_usage.get("total_tokens"),
            "prompt_tokens": token_usage.get("prompt_tokens"),
            "completion_tokens": token_usage.get("completion_tokens"),
            "successful_requests": token_usage.get("successful_requests"),
            "total_cost_usd": token_usage.get("total_cost_usd"),
            "has_estimated_usage": token_usage.get("has_estimated_usage"),
            "usage_by_component": token_usage.get("components"),
            "bug_collection_status": args.bug_collection_status,
            "answer": answer,
            "error": error,
        }
        rows.append(row)
        print(
            f"[{index}/{len(examples)}] {row['test_id']} "
            f"core_coverage={row['required_core_info_coverage']} action_match={row['action_match']} "
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
