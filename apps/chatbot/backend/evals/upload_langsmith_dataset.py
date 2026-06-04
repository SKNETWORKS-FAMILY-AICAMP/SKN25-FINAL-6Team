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


def upload_dataset(path: Path, *, dataset_name: str, description: str, recreate: bool) -> None:
    rows = _load_jsonl(path)
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
    parser = argparse.ArgumentParser(description="Upload chatbot regression JSONL to LangSmith.")
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
