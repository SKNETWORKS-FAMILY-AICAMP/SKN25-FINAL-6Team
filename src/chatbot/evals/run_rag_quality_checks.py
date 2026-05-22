from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Callable

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot.chains import persistence
from chatbot.chains.routing import route_by_category
from chatbot.generation import faq_agent
from chatbot.generation.orchestrator import _route_from_intent
from chatbot.retrieval import vector_tools
from chatbot.retrieval.vector_tools import hybrid_rank_documents, search_document_chunks
from chatbot.schemas import RoutingIntent


Check = tuple[str, Callable[[], None]]


def _assert_equal(actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"expected={expected!r}, actual={actual!r}")


def _routing_checks() -> list[Check]:
    return [
        (
            "갤럭시 결제 방법 안내 -> FAQ/RAG",
            lambda: _assert_equal(
                _route_from_intent(
                    RoutingIntent(
                        intent="payment_how_to",
                        normalized_query="갤럭시 스토어 결제 방법",
                        requires_account_lookup=False,
                        should_use_rag=True,
                        reason="general payment how-to",
                    ),
                    account_id=None,
                ),
                ("FAQ", "rag_reply", "intent:payment_how_to; general payment how-to"),
            ),
        ),
        (
            "갤럭시 결제 미지급 -> 결제/운영 확인",
            lambda: _assert_equal(
                _route_from_intent(
                    RoutingIntent(
                        intent="payment_missing_item",
                        normalized_query="결제 상품 미지급",
                        requires_account_lookup=True,
                        should_use_rag=False,
                        reason="paid item missing",
                    ),
                    account_id=None,
                ),
                ("결제", "urgent_alert", "intent:payment_missing_item; paid item missing"),
            ),
        ),
        (
            "계정 기반 결제 질문 -> 결제/운영 확인",
            lambda: _assert_equal(
                route_by_category({"category": "결제"}),
                "payment_agent",
            ),
        ),
    ]


def _search_checks() -> list[Check]:
    def check_faq_fallback() -> None:
        original = vector_tools._fetch_candidate_rows
        calls: list[tuple[bool, bool]] = []

        def fake_fetch_candidate_rows(*, retrieval_query, candidate_limit, faq_only, enrichment=None, use_query_filter=True):
            calls.append((faq_only, use_query_filter))
            if faq_only:
                return []
            return [
                {
                    "chunk_id": "fallback-doc",
                    "document_id": "doc-1",
                    "source_type": "notice",
                    "category": "general",
                    "title": "fallback",
                    "chunk_text": "payment item delivery fallback",
                    "embedding_vector": "[1.0,0.0]",
                }
            ]

        vector_tools._fetch_candidate_rows = fake_fetch_candidate_rows
        try:
            results = search_document_chunks(
                embedding_json="[1.0,0.0]",
                query_text="payment item delivery",
                top_k=1,
                prefer_faq=True,
            )
        finally:
            vector_tools._fetch_candidate_rows = original

        _assert_equal(calls, [(True, True), (True, False), (False, True)])
        _assert_equal(results[0]["candidate_scope"], "all")

    def check_hybrid_scores() -> None:
        results = hybrid_rank_documents(
            query_vector=[1.0, 0.0],
            query_text="payment item delivery",
            rows=[
                {
                    "chunk_id": "dense-match",
                    "document_id": "doc-1",
                    "source_type": "faq",
                    "category": "account",
                    "title": "account guide",
                    "chunk_text": "account linking and data deletion process",
                    "embedding_vector": "[1.0,0.0]",
                },
                {
                    "chunk_id": "keyword-match",
                    "document_id": "doc-2",
                    "source_type": "faq",
                    "category": "payment",
                    "title": "payment delivery guide",
                    "chunk_text": "payment item delivery missing check method",
                    "embedding_vector": "[0.0,1.0]",
                },
            ],
            top_k=2,
        )
        if not all("cosine_score" in result and "bm25_score" in result for result in results):
            raise AssertionError("hybrid scores are missing")

    return [
        ("FAQ 문서 우선 검색", lambda: _assert_equal(route_by_category({"category": "FAQ"}), "faq_agent")),
        ("FAQ 결과 없으면 전체 문서 fallback", check_faq_fallback),
        ("BM25 + cosine 점수 포함", check_hybrid_scores),
    ]


def _answer_checks() -> list[Check]:
    state = {
        "ticket_id": 123,
        "raw_query": "payment item delivery",
        "enriched_query": "payment item delivery",
        "category": "FAQ",
        "routing_target": "rag_reply",
        "retry_count": 0,
    }

    def check_no_docs_blocks_llm() -> None:
        original_embed = faq_agent._embed_query
        original_search = faq_agent.search_document_chunks
        original_rerank = faq_agent._rerank_documents
        original_failed = faq_agent._write_failed_query
        original_generate = faq_agent._generate_evidence_answer

        faq_agent._embed_query = lambda text: "[1.0,0.0]"
        faq_agent.search_document_chunks = lambda **kwargs: []
        faq_agent._rerank_documents = lambda documents, query: documents
        faq_agent._write_failed_query = lambda payload: "{}"

        def fail_generate(*args, **kwargs):
            raise AssertionError("LLM was called without evidence")

        faq_agent._generate_evidence_answer = fail_generate
        try:
            result = faq_agent.run_faq_rag(state)
        finally:
            faq_agent._embed_query = original_embed
            faq_agent.search_document_chunks = original_search
            faq_agent._rerank_documents = original_rerank
            faq_agent._write_failed_query = original_failed
            faq_agent._generate_evidence_answer = original_generate

        _assert_equal(result["faq_failure_reason"], "no_retrieved_documents")

    def check_evidence_generates_once() -> None:
        original_embed = faq_agent._embed_query
        original_search = faq_agent.search_document_chunks
        original_rerank = faq_agent._rerank_documents
        original_generate = faq_agent._generate_evidence_answer
        calls: list[object] = []

        docs = [
            {
                "chunk_id": "doc-1",
                "source_type": "hoyoverse_qna_common",
                "category": "결제_관련_이슈",
                "title": "payment guide",
                "chunk_text": "payment item delivery can be checked in logs",
                "score": 0.03,
            }
        ]
        faq_agent._embed_query = lambda text: "[1.0,0.0]"
        faq_agent.search_document_chunks = lambda **kwargs: docs
        faq_agent._rerank_documents = lambda documents, query: documents
        faq_agent._generate_evidence_answer = lambda query, documents: calls.append((query, documents)) or "answer"
        try:
            result = faq_agent.run_faq_rag(state)
        finally:
            faq_agent._embed_query = original_embed
            faq_agent.search_document_chunks = original_search
            faq_agent._rerank_documents = original_rerank
            faq_agent._generate_evidence_answer = original_generate

        _assert_equal(result["draft_text"], "answer")
        _assert_equal(len(calls), 1)

    return [
        ("검색 결과 0개면 LLM 호출 안 함", check_no_docs_blocks_llm),
        ("근거 문서가 있을 때만 답변 생성", check_evidence_generates_once),
    ]


def _evidence_checks() -> list[Check]:
    base_state = {
        "ticket_id": 1,
        "analysis_id": 2,
        "draft_text": "draft answer",
        "reasoning_node": "faq_agent",
        "category": "FAQ",
        "routing_target": "rag_reply",
    }

    def check_retrieved_docs_saved() -> None:
        original_draft = persistence._write_answer_draft
        original_evidence = persistence._write_evidence_doc
        payloads = []
        persistence._write_answer_draft = lambda payload: json.dumps({"draft_id": 10})
        persistence._write_evidence_doc = lambda payload: payloads.append(payload) or "{}"
        try:
            result = persistence.draft_persistence_node(
                {
                    **base_state,
                    "retrieved_documents": [
                        {
                            "chunk_id": "chunk-1",
                            "source_type": "hoyoverse_qna_common",
                            "chunk_text": "first evidence",
                            "score": 0.05,
                        }
                    ],
                }
            )
        finally:
            persistence._write_answer_draft = original_draft
            persistence._write_evidence_doc = original_evidence

        _assert_equal(result["evidence_count"], 1)
        _assert_equal(payloads[0]["source_id"], "chunk-1")

    def check_fallback_evidence_saved() -> None:
        original_draft = persistence._write_answer_draft
        original_evidence = persistence._write_evidence_doc
        payloads = []
        persistence._write_answer_draft = lambda payload: json.dumps({"draft_id": 11})
        persistence._write_evidence_doc = lambda payload: payloads.append(payload) or "{}"
        try:
            result = persistence.draft_persistence_node(base_state)
        finally:
            persistence._write_answer_draft = original_draft
            persistence._write_evidence_doc = original_evidence

        _assert_equal(result["evidence_count"], 1)
        _assert_equal(payloads[0]["source_type"], "agent")

    return [
        ("retrieved_documents를 evidence_docs로 저장", check_retrieved_docs_saved),
        ("근거 없으면 fallback evidence 저장", check_fallback_evidence_saved),
    ]


def _print_section(title: str, checks: list[Check]) -> bool:
    print(f"\n[{title}]")
    ok = True
    for label, check in checks:
        try:
            with redirect_stdout(StringIO()):
                check()
            print(f"PASS {label}")
        except Exception as exc:
            ok = False
            print(f"FAIL {label} - {exc}")
    return ok


def main() -> None:
    print("FAQ/RAG 품질 체크 결과")
    sections = [
        ("라우팅", _routing_checks()),
        ("검색", _search_checks()),
        ("답변 생성", _answer_checks()),
        ("근거 저장", _evidence_checks()),
    ]
    success = all(_print_section(title, checks) for title, checks in sections)
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
