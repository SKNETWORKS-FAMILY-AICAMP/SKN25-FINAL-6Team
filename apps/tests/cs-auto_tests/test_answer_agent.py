from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[3]
os.environ.setdefault("CS_AUTO_KEYWORD_DIR", str(ROOT_DIR / "data" / "keywords"))
os.environ.setdefault("CS_AUTO_SQL_DIR", str(ROOT_DIR / "data" / "sql"))
for path in reversed(
    [
        ROOT_DIR,
        ROOT_DIR / "apps" / "cs_auto" / "backend",
        ROOT_DIR / "packages" / "common-python" / "src",
    ]
):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from agents import analysis_agent  # noqa: E402
from agents import answer_agent  # noqa: E402
from common.db.connection import db_connection  # noqa: E402


HARD_CODED_KOREAN_INQUIRY = {
    "title": "결제는 됐는데 아이템이 안 들어왔어요",
    "raw_query": "패키지 결제는 완료됐는데 인벤토리나 우편함 어디에도 아이템이 들어오지 않았습니다. 확인 부탁드립니다.",
}

LLM_FALLBACK_DRAFT_TEXT = "결제 내역과 지급 지연 가능성을 확인 중입니다. 잠시 후 다시 확인해 주시고, 문제가 계속되면 운영팀 검토 후 추가로 안내드리겠습니다."


def _print_json(title: str, payload: object) -> None:
    print(f"\n[{title}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _trim_error(message: str) -> str:
    return " ".join(message.split())[:300]


def _fallback_routing_target(category: str) -> str:
    if category in {"payment", "refund", "account", "bug", "gacha"}:
        return "DB&DOC"
    if category == "policy":
        return "doc_only"
    return "fixed_answer"


def _require_live_env() -> None:
    required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "LLM_API_KEY", "LLM_MODEL"]
    missing = [key for key in required if not os.environ.get(key, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required env vars for live answer-agent test: {', '.join(missing)}")


def _load_live_sample_scope() -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    q.ticket_id,
                    q.account_id,
                    q.user_id,
                    q.source_type,
                    q.status,
                    q.session_id,
                    q.inquiry_created_at
                FROM qa_ticket q
                WHERE q.source_type = 'naver_cafe'
                  AND q.account_id IS NOT NULL
                  AND q.user_id IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM payments p
                      WHERE p.account_id = q.account_id
                  )
                ORDER BY q.inquiry_created_at DESC NULLS LAST, q.ticket_id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    if row is None:
        raise RuntimeError("No live qa_ticket sample found with payment-linked account scope.")
    return dict(row)


def _build_live_ticket() -> dict[str, Any]:
    scope = _load_live_sample_scope()
    ticket = {
        "ticket_id": int(scope["ticket_id"]),
        "account_id": int(scope["account_id"]),
        "user_id": int(scope["user_id"]),
        "title": HARD_CODED_KOREAN_INQUIRY["title"],
        "raw_query": HARD_CODED_KOREAN_INQUIRY["raw_query"],
        "source_type": str(scope["source_type"]),
        "status": "open",
        "session_id": scope.get("session_id"),
        "inquiry_created_at": scope.get("inquiry_created_at"),
    }
    _print_json("1. live DB scope + hardcoded Korean inquiry", ticket)
    return ticket


def _run_analysis_step_by_step(ticket: dict[str, Any]) -> dict[str, Any]:
    ticket_payload = analysis_agent._to_ticket_payload(ticket)
    _print_json("2. qa_ticket payload", ticket_payload.model_dump())

    enriched = analysis_agent._build_enriched_ticket(ticket_payload)
    _print_json(
        "3. enriched ticket",
        {
            "ticket_id": enriched.ticket.ticket_id,
            "enriched_query": enriched.enriched_query,
            "normalized_query": enriched.normalized_query,
        },
    )

    category_prompt_input = analysis_agent._build_category_prompt_input(enriched)
    _print_json("4. category prompt input", category_prompt_input)

    category = analysis_agent._classify_category(enriched)
    print(f"\n[5. category result]\n{category}")

    sentiment = analysis_agent._score_sentiment(enriched)
    print(f"\n[6. sentiment result]\n{sentiment}")

    risk_level = analysis_agent._score_risk(enriched, category)
    print(f"\n[7. risk result]\n{risk_level}")

    routing_input = {
        "enriched": enriched,
        "category": category,
        "sentiment": sentiment,
        "risk_level": risk_level,
    }
    _print_json("8. routing prompt input", analysis_agent._build_routing_prompt_input(routing_input))

    try:
        routed = analysis_agent._add_routing_target(routing_input)
        routing_mode = "llm"
    except Exception as exc:
        routed = {**routing_input, "routing_target": _fallback_routing_target(category)}
        routing_mode = f"fallback: {_trim_error(str(exc))}"
    print(f"\n[9. routing target]\n{routed['routing_target']}")
    print(f"\n[9-1. routing mode]\n{routing_mode}")

    summary = analysis_agent._summarize(enriched, category, routed["routing_target"], sentiment, risk_level)
    print(f"\n[10. analysis summary]\n{summary}")

    result = analysis_agent.AnalysisResult(
        ticket_id=ticket_payload.ticket_id,
        category=category,
        enriched_query=enriched.enriched_query,
        risk_level=risk_level,
        sentiment=sentiment,
        routing_target=routed["routing_target"],
        summary=summary,
    ).model_dump()
    _print_json("11. ticket_analysis result", result)
    return result


def _run_answer_step_by_step(ticket: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    target_payload = {
        **ticket,
        **analysis,
    }
    _print_json("12. merged qa_ticket + ticket_analysis payload", target_payload)

    target = answer_agent.AnswerTarget.model_validate(target_payload)
    _print_json("13. answer target", target.model_dump())

    collector = answer_agent.AnswerEvidenceCollector()
    ticket_payload = collector._ticket_payload(target)
    analysis_payload = collector._analysis_payload(target)
    _print_json("14. answer collector qa_ticket payload", ticket_payload)
    _print_json("15. answer collector ticket_analysis payload", analysis_payload)

    routing_target = str(target.routing_target or "fixed_answer")
    evidence_docs: list[dict[str, Any]] = []

    if routing_target in {"DB_only", "DB&DOC"}:
        try:
            db_decision = collector.db_router.decide_query_type(ticket_payload, analysis_payload)
            _print_json("16. DB router decision", db_decision.model_dump())
            db_result = collector.db_router.run(ticket_payload, analysis_payload)
            db_mode = "router"
        except Exception as exc:
            db_mode = f"fixed_sql fallback: {_trim_error(str(exc))}"
            db_result = collector.db_router.fixed_sql.run(ticket_payload, analysis_payload)
        _print_json(
            "17. DB search result",
            {
                "query_type": db_result["query_type"],
                "sql": db_result["sql"],
                "params": db_result["params"],
                "plan": db_result["plan"],
                "row_count": len(db_result["rows"]),
                "rows_preview": db_result["rows"][:3],
                "evidence_preview": db_result["evidence"][:3],
            },
        )
        print(f"\n[17-1. DB mode]\n{db_mode}")
        evidence_docs.extend(list(db_result["evidence"]))

    if routing_target in {"doc_only", "DB&DOC"}:
        try:
            document_query = collector.doc_retriever.query_builder.build(ticket_payload, analysis_payload)
            _print_json("18. document query", document_query.model_dump())

            documents = collector.doc_retriever.document_searcher.search(document_query)
            _print_json(
                "19. retrieved documents",
                [document.model_dump() for document in documents[:5]],
            )

            doc_evidence = collector.doc_retriever.evidence_assembler.build(documents)
            _print_json("20. document evidence", doc_evidence[:5])
            print("\n[20-1. document mode]\nlive")
            evidence_docs.extend(doc_evidence)
        except Exception as exc:
            _print_json("19. retrieved documents", {"error": _trim_error(str(exc))})
            _print_json("20. document evidence", [])
            print(f"\n[20-1. document mode]\nskipped: {_trim_error(str(exc))}")

    if routing_target == "fixed_answer":
        evidence_docs = collector.collect_fixed_answer_context(analysis_payload)
        _print_json("18. fixed-answer evidence", evidence_docs)

    context = answer_agent.AnswerDraftContext(ticket=target, evidence_docs=evidence_docs)
    _print_json("21. answer draft context", context.model_dump())

    draft_generator = answer_agent.AnswerDraftGenerator()
    draft_prompt_input = draft_generator._build_prompt_input(context)
    _print_json("22. draft prompt input", draft_prompt_input)

    try:
        draft = draft_generator.generate(context)
        draft_mode = "llm"
    except Exception as exc:
        draft = answer_agent.AnswerDraftResult(
            draft_text=LLM_FALLBACK_DRAFT_TEXT,
            safety_label="review_required",
            review_reason="llm_generation_failed",
            used_evidence_count=len(evidence_docs),
            metadata={"draft_mode": "fallback", "llm_error": _trim_error(str(exc))},
        )
        draft_mode = f"fallback: {_trim_error(str(exc))}"
    _print_json("23. generated draft", draft.model_dump())
    print(f"\n[23-1. draft mode]\n{draft_mode}")

    safety_evaluator = answer_agent.AnswerSafetyEvaluator()
    safety_prompt_input = safety_evaluator._build_prompt_input({"context": context, "draft": draft})
    _print_json("24. safety prompt input", safety_prompt_input)

    try:
        safety = safety_evaluator.evaluate(context, draft)
        safety_mode = "llm"
    except Exception as exc:
        safety = answer_agent.AnswerSafetyResult(
            hallucination_score=0.4,
            toxicity_score=0.0,
            policy_violation_score=0.0,
            factuality_score=0.4,
            safety_action="fixed_answer",
            safety_reason="llm_safety_failed",
            retry_count=0,
            average_score=0.5,
        )
        safety_mode = f"fallback: {_trim_error(str(exc))}"
    _print_json("25. safety result", safety.model_dump())
    print(f"\n[25-1. safety mode]\n{safety_mode}")

    routed_draft = answer_agent.AnswerSafetyRouter().route(context, draft, safety)
    _print_json("26. routed answer draft", routed_draft.model_dump())

    final_result = {
        "ticket_id": target.ticket_id,
        "routing_target": target.routing_target,
        "evidence_count": len(evidence_docs),
        "draft_text": routed_draft.draft_text,
        "safety_label": routed_draft.safety_label,
        "review_reason": routed_draft.review_reason,
        "safety": safety.model_dump(),
        "metadata": routed_draft.metadata,
    }
    _print_json("27. final live answer result", final_result)
    return final_result


def _run_live_answer_agent_trace() -> dict[str, Any]:
    _require_live_env()
    ticket = _build_live_ticket()
    analysis = _run_analysis_step_by_step(ticket)
    return _run_answer_step_by_step(ticket, analysis)


def test_answer_target_model_accepts_live_shape() -> None:
    payload = {
        "ticket_id": 1,
        "account_id": 2,
        "user_id": 3,
        "title": HARD_CODED_KOREAN_INQUIRY["title"],
        "raw_query": HARD_CODED_KOREAN_INQUIRY["raw_query"],
        "source_type": "naver_cafe",
        "status": "analyzed",
        "analysis_id": 10,
        "category": "payment",
        "enriched_query": HARD_CODED_KOREAN_INQUIRY["title"],
        "risk_level": "MID",
        "sentiment": "negative",
        "routing_target": "DB&DOC",
        "summary": "summary",
    }

    target = answer_agent.AnswerTarget.model_validate(payload)

    assert target.ticket_id == 1
    assert target.category == "payment"
    assert target.routing_target == "DB&DOC"


def test_answer_safety_router_uses_fixed_answer_when_safety_fails() -> None:
    target = answer_agent.AnswerTarget.model_validate(
        {
            "ticket_id": 1,
            "title": HARD_CODED_KOREAN_INQUIRY["title"],
            "raw_query": HARD_CODED_KOREAN_INQUIRY["raw_query"],
            "category": "payment",
            "routing_target": "fixed_answer",
            "summary": "summary",
        }
    )
    context = answer_agent.AnswerDraftContext(
        ticket=target,
        evidence_docs=[
            {
                "source_type": "fixed_answer",
                "source_id": "fallback_1",
                "evidence_text": "문의 내용을 확인했습니다. 정확한 안내를 위해 운영팀이 검토 후 다시 안내드리겠습니다.",
                "relevance_score": 1.0,
                "retrieval_rank": 1,
            }
        ],
    )
    draft = answer_agent.AnswerDraftResult(
        draft_text="temporary",
        used_evidence_count=1,
        metadata={},
    )
    safety = answer_agent.AnswerSafetyResult(
        hallucination_score=0.8,
        toxicity_score=0.0,
        policy_violation_score=0.0,
        factuality_score=0.1,
        safety_action="fixed_answer",
        safety_reason="low_safety_average_score",
        retry_count=0,
        average_score=0.3,
    )

    routed = answer_agent.AnswerSafetyRouter().route(context, draft, safety)

    assert "운영팀이 검토" in routed.draft_text
    assert routed.safety_label == "review_required"


def test_live_answer_agent_with_real_db_and_llm() -> None:
    r"""실제 DB/LLM을 사용해 answer_agent 단계를 터미널에 출력한다.

    실행 예:
    $env:CS_AUTO_RUN_LIVE_TESTS="1"
    python -m pytest apps\tests\cs-auto_tests\test_answer_agent.py -s
    """

    if os.environ.get("CS_AUTO_RUN_LIVE_TESTS", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("Set CS_AUTO_RUN_LIVE_TESTS=1 to run the live DB/LLM answer-agent trace.")

    result = _run_live_answer_agent_trace()

    assert result["ticket_id"] > 0
    assert result["evidence_count"] >= 1
    assert result["draft_text"].strip() != ""
    assert result["safety"]["average_score"] >= 0.0


if __name__ == "__main__":
    _run_live_answer_agent_trace()
