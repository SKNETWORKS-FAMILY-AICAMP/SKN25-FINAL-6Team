from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT_PATH = Path(__file__).parent / "datasets" / "gameops-chatbot-e2e-workflow-22-v1.json"
DEFAULT_OUTPUT_PATH = Path(__file__).parent / "datasets" / "gameops-chatbot-e2e-workflow-22-v1.normalized.json"
EVIDENCE_LABEL_MAP = {
    "account_policy": "policy_document",
    "payment_policy": "policy_document",
    "security_policy": "policy_document",
    "privacy_policy": "policy_document",
    "event_notice": "notice_document",
    "maintenance_notice": "notice_document",
    "attendance_event_notice": "notice_document",
    "package_guide": "game_guide",
    "ranking_reward_guide": "game_guide",
    "patch_note": "game_guide",
    "event_participation_logs": "item_delivery_logs",
    "account_reward_logs": "item_delivery_logs",
    "ranking_logs": "item_delivery_logs",
    "attendance_logs": "item_delivery_logs",
    "quest_progress_logs": "bug_report_context",
}
ALLOWED_EVIDENCE_LABELS = {
    "faq_document",
    "policy_document",
    "notice_document",
    "game_guide",
    "payments",
    "refunds",
    "item_delivery_logs",
    "gacha_logs",
    "bug_report_context",
    "redis_retrieval_cache",
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_json(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    examples = data.get("examples") if isinstance(data, dict) else data
    if not isinstance(examples, list):
        raise ValueError(f"Unsupported JSON dataset shape: {path}")
    metadata = data if isinstance(data, dict) else {}
    return metadata, examples


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    outputs = dict(normalized.get("outputs") or {})
    metadata = dict(normalized.get("metadata") or {})

    normalized_evidence = []
    for label in outputs.get("required_evidence_types") or []:
        mapped = EVIDENCE_LABEL_MAP.get(label, label)
        if mapped in ALLOWED_EVIDENCE_LABELS and mapped not in normalized_evidence:
            normalized_evidence.append(mapped)

    outputs["required_evidence_types"] = normalized_evidence
    outputs.setdefault("requires_rag", bool(metadata.get("requires_rag")))
    outputs.setdefault("test_type", metadata.get("test_type"))
    normalized["outputs"] = outputs
    normalized["metadata"] = metadata
    return normalized


def load_rows(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if path.suffix == ".jsonl":
        return {"dataset_info": {"source": str(path)}}, [_normalize_row(row) for row in _load_jsonl(path)]
    if path.suffix == ".json":
        metadata, rows = _load_json(path)
        return metadata, [_normalize_row(row) for row in rows]
    raise ValueError(f"Unsupported dataset extension: {path.suffix}")


def write_dataset(input_path: Path, output_path: Path) -> int:
    metadata, rows = load_rows(input_path)
    payload = dict(metadata)
    payload["examples"] = rows
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize chatbot eval datasets for local Langfuse-traced evaluation."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    count = write_dataset(args.input, args.output)
    print(f"Normalized {count} examples")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
