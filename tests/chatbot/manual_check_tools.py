from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from chatbot.tools.cache_tools import get_cache, set_cache
from chatbot.notifications.dispatcher import dispatch_urgent_alert
from chatbot.repositories.base import safe_read, safe_write
from chatbot.tools.db_tools import read_gacha_logs, read_item_delivery_logs, write_voc_feedback
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

    _print_json(
        "voc feedback write",
        write_voc_feedback.invoke({
            "payload": {
                "ticket_id": 1005,
                "user_id": 1,
                "account_id": 101,
                "voc_type": "complaint",
                "sentiment": "negative",
                "raw_content": "이번 이벤트 보상이 너무 적어서 불만이에요.",
                "topic_keywords": ["이벤트", "보상", "불만"],
            },
        }),
    )


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


def check_observability_logs() -> None:
    print("\n=== Observability Logs ===")
    print("\n[forced db read failure log]")
    result = safe_read(
        operation="read_payments",
        ticket_id=1998,
        reader=lambda: (_ for _ in ()).throw(
            TimeoutError("payment DB read timed out")
        ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n[forced db write failure log]")
    result = safe_write(
        operation="write_answer_draft",
        payload={"ticket_id": 1999},
        writer=lambda: (_ for _ in ()).throw(
            RuntimeError("could not connect to server: Connection refused")
        ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n[urgent alert notification mock log]")
    result = dispatch_urgent_alert({
        "ticket_id": 2001,
        "session_id": "manual-session",
        "category": "결제",
        "routing_target": "urgent_alert",
        "raw_content": "결제했는데 아이템이 안 들어왔어요.",
        "final_answer": "문의가 접수되었습니다. 담당자가 확인 후 안내드리겠습니다.",
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    check_cache_tools()
    check_db_tools()
    check_vector_tools()
    check_observability_logs()


if __name__ == "__main__":
    main()
