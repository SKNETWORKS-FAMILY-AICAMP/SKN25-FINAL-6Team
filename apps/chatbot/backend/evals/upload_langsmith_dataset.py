from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import Client


DEFAULT_DATASET_PATH = Path(__file__).parent / "datasets" / "gameops-chatbot-regression-v1.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[4]
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


def load_chatbot_langsmith_env() -> None:
    """Load repo .env and map chatbot-specific LangSmith env names to SDK names."""
    load_dotenv(REPO_ROOT / ".env", override=True)
    mappings = {
        "CHATBOT_LANGSMITH_API_KEY": "LANGSMITH_API_KEY",
        "CHATBOT_LANGSMITH_PROJECT": "LANGSMITH_PROJECT",
        "CHATBOT_LANGSMITH_TRACING": "LANGSMITH_TRACING",
    }
    for source, target in mappings.items():
        value = os.environ.get(source)
        if value:
            os.environ[target] = value
    if os.environ.get("LANGSMITH_TRACING"):
        os.environ["LANGCHAIN_TRACING_V2"] = os.environ["LANGSMITH_TRACING"]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_json(path: Path) -> list[dict[str, Any]]:
    """Load either a plain list of LangSmith examples or a wrapped dataset JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("examples"), list):
        return data["examples"]
    raise ValueError(f"Unsupported JSON dataset shape: {path}")


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    outputs = row.setdefault("outputs", {})
    metadata = row.get("metadata") or {}
    normalized_evidence = []
    for label in outputs.get("required_evidence_types") or []:
        mapped = EVIDENCE_LABEL_MAP.get(label, label)
        if mapped in ALLOWED_EVIDENCE_LABELS and mapped not in normalized_evidence:
            normalized_evidence.append(mapped)
    outputs["required_evidence_types"] = normalized_evidence
    outputs.setdefault("requires_rag", bool(metadata.get("requires_rag")))
    outputs.setdefault("test_type", metadata.get("test_type"))
    return row


def _load_rows(path: Path) -> list[dict[str, Any]]:
    """Accept JSONL for existing flow and JSON for paper-based curated datasets."""
    if path.suffix == ".jsonl":
        return [_normalize_row(row) for row in _load_jsonl(path)]
    if path.suffix == ".json":
        return [_normalize_row(row) for row in _load_json(path)]
    raise ValueError(f"Unsupported dataset extension: {path.suffix}")


def upload_dataset(path: Path, *, dataset_name: str, description: str, recreate: bool) -> None:
    rows = _load_rows(path)
    if not rows:
        raise ValueError(f"No rows found in {path}")

    client = Client()
    if recreate:
        try:
            client.delete_dataset(dataset_name=dataset_name)
        except Exception:
            pass

    try:
        dataset = client.create_dataset(dataset_name=dataset_name, description=description)
    except Exception:
        dataset = client.read_dataset(dataset_name=dataset_name)

    client.create_examples(
        dataset_id=dataset.id,
        inputs=[row["inputs"] for row in rows],
        outputs=[row.get("outputs") for row in rows],
        metadata=[row.get("metadata") for row in rows],
    )
    print(f"Uploaded {len(rows)} examples to LangSmith dataset: {dataset_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload chatbot regression JSON or JSONL to LangSmith.")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-name", default="gameops-chatbot-regression-v1")
    parser.add_argument(
        "--description",
        default="Game CS chatbot regression set for routing, RAG, DB reasoning, dashboard, and safety evaluation.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete the existing LangSmith dataset with the same name before uploading.",
    )
    args = parser.parse_args()

    load_chatbot_langsmith_env()
    upload_dataset(args.input, dataset_name=args.dataset_name, description=args.description, recreate=args.recreate)


if __name__ == "__main__":
    main()
