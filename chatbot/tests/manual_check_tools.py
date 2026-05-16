from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from chatbot.tools.cache_tools import get_cache, set_cache
from chatbot.tools.db_tools import read_gacha_logs, read_item_delivery_logs
from chatbot.tools.vector_tools import rerank_documents, search_documents
from data.seed_payload import SEED_DOCUMENT_EMBEDDINGS


def _print_json(title: str, raw: str) -> None:
    print(f"\n[{title}]")
    print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))


def check_cache_tools() -> None:
    print("\n=== Cache Tools ===")
    _print_json("cache miss", get_cache.invoke({"query_hash": "unknown"}))

    _print_json(
        "cache set",
        set_cache.invoke({
            "query_hash": "faq:event_reward",
            "answer": "이벤트 보상은 순차 지급됩니다.",
            "ttl": 3600,
        }),
    )
    _print_json("cache hit", get_cache.invoke({"query_hash": "faq:event_reward"}))

    _print_json(
        "expired cache set",
        set_cache.invoke({
            "query_hash": "faq:expired",
            "answer": "만료될 답변입니다.",
            "ttl": -1,
        }),
    )
    _print_json("expired cache miss", get_cache.invoke({"query_hash": "faq:expired"}))


def check_db_tools() -> None:
    print("\n=== DB Read Tools ===")
    _print_json("gacha logs account_id=102", read_gacha_logs.invoke({"account_id": 102}))
    _print_json(
        "delivery logs account_id=102",
        read_item_delivery_logs.invoke({"account_id": 102}),
    )
    _print_json("gacha logs account_id=999", read_gacha_logs.invoke({"account_id": 999}))


def check_vector_tools() -> None:
    print("\n=== Vector Tools ===")
    seed = SEED_DOCUMENT_EMBEDDINGS[0]
    embedding_json = json.dumps(seed["embedding_vector"])

    raw_results = search_documents.invoke({
        "embedding_json": embedding_json,
        "top_k": 3,
    })
    _print_json("seed embedding search top_k=3", raw_results)

    results = json.loads(raw_results)
    print("\n[vector summary]")
    print(f"expected chunk_id: {seed['chunk_id']}")
    print(f"actual top_1 chunk_id: {results[0]['chunk_id'] if results else None}")
    print(f"actual top_1 score: {results[0]['score'] if results else None}")

    docs_json = json.dumps([
        {"chunk_id": "FAQ-101-1", "score": 1.0},
        {"chunk_id": "FAQ-102-1", "score": 0.8},
    ])
    _print_json(
        "rerank pass-through",
        rerank_documents.invoke({"docs_json": docs_json, "query": "결제 보상"}),
    )


def main() -> None:
    check_cache_tools()
    check_db_tools()
    check_vector_tools()


if __name__ == "__main__":
    main()
