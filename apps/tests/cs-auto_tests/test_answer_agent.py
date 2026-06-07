from __future__ import annotations

from agents import answer_agent as agent


def _target(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticket_id": 1,
        "account_id": 10,
        "user_id": 20,
        "title": "결제 문의",
        "raw_query": "결제했는데 상품이 없습니다.",
        "source_type": "naver_cafe",
        "status": "analyzed",
        "analysis_id": 100,
        "category": "payment",
        "enriched_query": "결제 상품 미지급",
        "risk_level": "MID",
        "sentiment": "neutral",
        "routing_target": "DB&DOC",
        "summary": "payment summary",
    }
    payload.update(overrides)
    return payload


def _evidence() -> list[dict[str, object]]:
    return [
        {
            "source_type": "payments",
            "source_id": "1",
            "evidence_text": "payment_status=paid",
            "relevance_score": 0.9,
            "retrieval_rank": 1,
        }
    ]


def test_select_retrieval_strategy_for_all_routes() -> None:
    assert agent.select_retrieval_strategy({"routing_target": "DB_only"}) == {
        "routing_target": "DB_only",
        "use_documents": False,
        "use_operation_logs": True,
        "fixed_answer": False,
    }
    assert agent.select_retrieval_strategy({"routing_target": "doc_only"})["use_documents"] is True
    assert agent.select_retrieval_strategy({"routing_target": "DB&DOC"})["use_operation_logs"] is True
    assert agent.select_retrieval_strategy({"routing_target": "human_review"})["fixed_answer"] is True


def test_generate_answer_draft_text_includes_evidence_and_regeneration_reason() -> None:
    draft = agent.generate_answer_draft_text(
        _target(),
        _target(),
        _evidence(),
        regeneration_reason="더 정중하게 작성",
    )

    assert "안녕하세요. 게임 고객지원팀입니다." in draft
    assert "[payments] payment_status=paid" in draft
    assert "재생성 요청 반영 사항" in draft


def test_evaluate_answer_safety_routes_missing_evidence_to_human_review() -> None:
    result = agent.evaluate_answer_safety({"ticket_id": 1}, [])

    assert result["safety_action"] == "human_review"
    assert result["safety_reason"] == "missing_evidence"
    assert result["hallucination_score"] > result["factuality_score"]


def test_evaluate_answer_safety_with_evidence_is_ready_for_review() -> None:
    result = agent.evaluate_answer_safety({"ticket_id": 1}, _evidence())

    assert result["safety_action"] == "ready_for_review"
    assert result["factuality_score"] == 0.9


def test_collect_answer_evidence_delegates_to_retrieval_router(monkeypatch) -> None:
    class FakeRouter:
        def retrieve_by_routing_target(self, ticket, analysis):
            return [{"source_type": analysis["routing_target"], "ticket_id": ticket["ticket_id"]}]

    monkeypatch.setattr(agent, "RetrievalRouter", lambda: FakeRouter())

    evidence = agent.collect_answer_evidence(_target(), _target(routing_target="DB_only"), {"routing_target": "DB_only"})

    assert evidence == [{"source_type": "DB_only", "ticket_id": 1}]


def test_answer_generation_chain_builds_context_draft_and_safety(monkeypatch) -> None:
    monkeypatch.setattr(agent, "collect_answer_evidence", lambda ticket, analysis, strategy: _evidence())

    result = agent.ANSWER_CHAIN.invoke(_target())

    assert result.context.ticket.ticket_id == 1
    assert result.context.evidence_docs[0].source_type == "payments"
    assert result.safety.safety_action == "ready_for_review"
    assert "payment_status=paid" in result.draft_text


def test_regeneration_chain_uses_existing_context() -> None:
    context = {
        "ticket": _target(),
        "analysis": _target(),
        "evidence_docs": _evidence(),
    }

    result = agent.REGENERATION_CHAIN.invoke({"context": context, "regeneration_reason": "간결하게"})

    assert result.context.regeneration_reason == "간결하게"
    assert "재생성 요청 반영 사항" in result.draft_text


def test_process_answer_target_orchestrates_persistence(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(agent, "collect_answer_evidence", lambda ticket, analysis, strategy: _evidence())
    monkeypatch.setattr(
        agent,
        "save_answer_draft",
        lambda ticket, analysis, draft_text: calls.append(("draft", ticket["ticket_id"]))
        or {"draft_id": 55, "ticket_id": ticket["ticket_id"], "analysis_id": analysis["analysis_id"], "draft_text": draft_text},
    )
    monkeypatch.setattr(
        agent,
        "save_evidence_docs",
        lambda draft_id, evidence_docs: calls.append(("evidence", draft_id)) or evidence_docs,
    )
    monkeypatch.setattr(
        agent,
        "save_safety_results",
        lambda draft_id, safety_result: calls.append(("safety", draft_id)) or safety_result,
    )
    monkeypatch.setattr(
        agent,
        "route_by_safety_result",
        lambda ticket, analysis, draft, safety: calls.append(("route", safety["safety_action"])),
    )

    agent.process_answer_target(_target())

    assert calls == [("draft", 1), ("evidence", 55), ("safety", 55), ("route", "ready_for_review")]


def test_regenerate_agent_respects_limit_and_saves_new_draft(monkeypatch) -> None:
    monkeypatch.setattr(agent, "validate_regeneration_limit", lambda ticket_id: {"can_regenerate": True, "retry_count": 1})
    monkeypatch.setattr(agent, "fetch_regeneration_context", lambda ticket_id: {"ticket": _target(), "analysis": _target(), "evidence_docs": _evidence()})
    monkeypatch.setattr(agent, "save_answer_draft", lambda ticket, analysis, draft_text: {"draft_id": 77, "ticket_id": ticket["ticket_id"]})
    monkeypatch.setattr(agent, "save_evidence_docs", lambda draft_id, evidence_docs: evidence_docs)
    monkeypatch.setattr(agent, "save_safety_results", lambda draft_id, safety_result: {"retry_count": safety_result["retry_count"]})

    result = agent.regenerate_agent(1, "정중하게")

    assert result is not None
    assert result["draft"]["draft_id"] == 77
    assert result["retry_count"] == 2
    assert result["safety"]["retry_count"] == 2


def test_build_regeneration_prompt_context_preserves_inputs() -> None:
    context = {"ticket": {"ticket_id": 1}, "analysis": {"analysis_id": 2}, "draft": {"draft_id": 3}, "evidence_docs": _evidence()}

    result = agent.build_regeneration_prompt_context(context, "다시 작성")

    assert result["ticket"] == {"ticket_id": 1}
    assert result["regeneration_reason"] == "다시 작성"

