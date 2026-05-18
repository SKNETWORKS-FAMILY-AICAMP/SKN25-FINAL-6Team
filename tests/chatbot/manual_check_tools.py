from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.notifications import slack as slack_module
from chatbot.notifications.dispatcher import dispatch_urgent_alert
from chatbot.notifications.slack import send_slack_alert
from chatbot.observability.error_classifier import classify_error
from chatbot.observability.logger import EVENT_DB_WRITE_FAILED, build_log_event, log_event
from chatbot.repositories.base import safe_read, safe_write
from chatbot.response.final_response import final_response_node
from chatbot.tools.cache_tools import get_cache, set_cache
from chatbot.tools.db_tools import (
    read_gacha_logs,
    read_item_delivery_logs,
    read_payments,
    write_failed_query,
    write_voc_feedback,
)
from chatbot.tools.vector_tools import rerank_documents, search_documents
from data.seed_payload import SEED_DOCUMENT_EMBEDDINGS


def _print_json(title: str, raw: str) -> None:
    print(f"\n[{title}]")
    print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))


def _print_dict(title: str, payload: dict) -> None:
    print(f"\n[{title}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


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
    print("\n=== DB Tools ===")
    _print_json("payments account_id=101", read_payments.invoke({"account_id": 101}))
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

    _print_json(
        "failed query write",
        write_failed_query.invoke({
            "payload": {
                "ticket_id": 1007,
                "query": "공월 축복이란 무엇인가요?",
                "category": "FAQ",
                "reason": "no reliable evidence",
            },
        }),
    )

    print("\n[forced answer draft write failure]")
    result = safe_write(
        operation="write_answer_draft",
        payload={"ticket_id": 9999, "content": "draft"},
        writer=lambda: (_ for _ in ()).throw(NotImplementedError("real DB write is not implemented")),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


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

    raw_top_2 = search_documents.invoke({
        "embedding_json": embedding_json,
        "top_k": 2,
    })
    results_top_2 = json.loads(raw_top_2)
    print("\n[top_k summary]")
    print(f"requested top_k: 2")
    print(f"actual count: {len(results_top_2)}")

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
    print("\n[error classifier samples]")
    for exc in (
        NotImplementedError("not ready"),
        TimeoutError("request timed out"),
        RuntimeError("could not connect to server: Connection refused"),
        RuntimeError("password authentication failed for user"),
        RuntimeError('relation "qa_ticket" does not exist'),
        RuntimeError("duplicate key value violates unique constraint"),
    ):
        print(f"{type(exc).__name__}: {exc} -> {classify_error(exc)}")

    _print_dict(
        "structured event",
        build_log_event(EVENT_DB_WRITE_FAILED, ticket_id=1001, status="error"),
    )

    print("\n[print json log event]")
    log_event(
        EVENT_DB_WRITE_FAILED,
        ticket_id=1001,
        session_id="manual-session",
        node_name="repository",
        category="결제",
        routing_target="urgent_alert",
        tool_name="write_answer_draft",
        status="error",
        error_message="forced failure",
        metadata={"error_type": "RuntimeError"},
    )

    print("\n[forced db read failure log]")
    result = safe_read(
        operation="read_payments",
        ticket_id=1998,
        reader=lambda: (_ for _ in ()).throw(TimeoutError("payment DB read timed out")),
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


def check_notifications() -> None:
    print("\n=== Notifications ===")
    original_webhook = os.environ.pop("SLACK_WEBHOOK_URL", None)
    try:
        print("\n[urgent alert notification mock]")
        result = dispatch_urgent_alert({
            "ticket_id": 2001,
            "session_id": "manual-session",
            "category": "결제",
            "routing_target": "urgent_alert",
            "raw_content": "결제했는데 아이템이 안 들어왔어요.",
            "final_answer": "문의가 접수되었습니다. 담당자가 확인 후 안내드리겠습니다.",
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))

        print("\n[non-urgent notification skipped]")
        result = dispatch_urgent_alert({
            "ticket_id": 2002,
            "session_id": "manual-session",
            "category": "FAQ",
            "routing_target": "rag_reply",
            "raw_content": "공월 축복이 뭐예요?",
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        if original_webhook is not None:
            os.environ["SLACK_WEBHOOK_URL"] = original_webhook

    print("\n[slack send failure classified]")
    original_urlopen = slack_module.request.urlopen
    os.environ["SLACK_WEBHOOK_URL"] = "https://example.invalid/webhook"
    try:
        slack_module.request.urlopen = lambda *args, **kwargs: (_ for _ in ()).throw(
            TimeoutError("request timed out")
        )
        result = send_slack_alert("긴급 문의 테스트")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        slack_module.request.urlopen = original_urlopen
        if original_webhook is None:
            os.environ.pop("SLACK_WEBHOOK_URL", None)
        else:
            os.environ["SLACK_WEBHOOK_URL"] = original_webhook


def check_final_response() -> None:
    print("\n=== Final Response ===")
    original_webhook = os.environ.pop("SLACK_WEBHOOK_URL", None)
    try:
        print("\n[urgent final response dispatches mock alert]")
        result = final_response_node({
            "ticket_id": 3001,
            "session_id": "manual-session",
            "category": "결제",
            "routing_target": "urgent_alert",
            "raw_content": "결제했는데 아이템이 안 들어왔어요.",
            "answer_draft": "담당자가 확인할 수 있도록 접수했습니다.",
            "safety_action": "AUTO_RESPONSE",
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))

        print("\n[non-urgent final response skips alert]")
        result = final_response_node({
            "ticket_id": 3002,
            "session_id": "manual-session",
            "category": "FAQ",
            "routing_target": "rag_reply",
            "raw_content": "공월 축복이 뭐예요?",
            "answer_draft": "공월 축복 안내입니다.",
            "safety_action": "AUTO_RESPONSE",
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        if original_webhook is None:
            os.environ.pop("SLACK_WEBHOOK_URL", None)
        else:
            os.environ["SLACK_WEBHOOK_URL"] = original_webhook


CHECKS = {
    "cache": check_cache_tools,
    "db": check_db_tools,
    "vector": check_vector_tools,
    "observability": check_observability_logs,
    "notifications": check_notifications,
    "final-response": check_final_response,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run manual chatbot tool checks.")
    parser.add_argument(
        "--section",
        choices=["all", *CHECKS.keys()],
        default="all",
        help="Manual check section to run.",
    )
    args = parser.parse_args()

    selected = CHECKS.values() if args.section == "all" else (CHECKS[args.section],)
    for check in selected:
        check()


if __name__ == "__main__":
    main()
