from __future__ import annotations

import json
import re
from pathlib import Path
import sys
from typing import Any

from langchain_openai import OpenAIEmbeddings


ROOT_DIR = Path(__file__).resolve().parent.parent
root_str = str(ROOT_DIR)

if root_str not in sys.path:
    sys.path.insert(0, root_str)

from config import settings
from data.seed_payload import (
    SEED_DOCUMENT_CHUNKS,
    SEED_DOCUMENT_EMBEDDINGS,
)


SEED_PAYLOAD_PATH = Path(__file__).with_name("seed_payload.py")


def _resolve_embedding_model_name(raw_model_name: str) -> str:
    if raw_model_name.startswith("openai:"):
        return raw_model_name.split(":", 1)[1]
    return raw_model_name


def _build_embedding_client() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=_resolve_embedding_model_name(settings.embedding_model),
        api_key=settings.openai_api_key,
    )


def build_seed_embedding_rows() -> list[dict[str, Any]]:
    chunk_by_id = {
        row["chunk_id"]: row
        for row in SEED_DOCUMENT_CHUNKS
    }

    embedding_rows = [
        dict(row)
        for row in SEED_DOCUMENT_EMBEDDINGS
    ]

    texts = [
        chunk_by_id[row["chunk_id"]]["chunk_text"]
        for row in embedding_rows
    ]

    client = _build_embedding_client()
    vectors = client.embed_documents(texts)

    for row, vector in zip(embedding_rows, vectors, strict=True):
        row["embedding_vector"] = vector
        row["embedding_model"] = settings.embedding_model

    return embedding_rows


def _replace_embedding_block(
    source_text: str,
    embedding_id: str,
    embedding_vector: list[float],
    embedding_model: str,
) -> str:
    vector_text = json.dumps(
        embedding_vector,
        ensure_ascii=False,
    )

    pattern = re.compile(
        rf'("embedding_id": "{re.escape(embedding_id)}",\n'
        rf'\s*"chunk_id": "[^"]+",\n'
        rf'\s*"embedding_vector": )\[[^\]]*\](,\n'
        rf'\s*"embedding_model": )"[^"]*"',
        re.MULTILINE,
    )

    return pattern.sub(
        rf'\1{vector_text}\2"{embedding_model}"',
        source_text,
        count=1,
    )


def write_embeddings_to_seed_payload(
    seed_payload_path: Path = SEED_PAYLOAD_PATH,
) -> list[dict[str, Any]]:
    updated_rows = build_seed_embedding_rows()

    source_text = seed_payload_path.read_text(
        encoding="utf-8",
    )

    for row in updated_rows:
        source_text = _replace_embedding_block(
            source_text=source_text,
            embedding_id=row["embedding_id"],
            embedding_vector=row["embedding_vector"],
            embedding_model=row["embedding_model"],
        )

    seed_payload_path.write_text(
        source_text,
        encoding="utf-8",
    )

    return updated_rows


def main() -> None:
    updated_rows = write_embeddings_to_seed_payload()

    print(
        f"Updated {len(updated_rows)} embedding rows "
        f"in {SEED_PAYLOAD_PATH.name}."
    )


if __name__ == "__main__":
    main()