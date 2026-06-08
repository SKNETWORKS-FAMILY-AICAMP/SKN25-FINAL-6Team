from __future__ import annotations

from datetime import datetime, timedelta

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
    assert agent.select_retrieval_strategy({"routing_target": "human_review"})["fixed_answer"] is False


def test_answer_agent_contract_documents_roles_and_models() -> None:
    contract = agent.get_answer_agent_contract()

    assert contract["role_steps"] == [
        "fetch_analyzed_ticket",
        "collect_evidence",
        "generate_answer_draft",
        "save_answer_draft",
        "save_evidence_docs",
        "save_safety_results",
        "route_by_safety_result",
    ]
    assert contract["answer_chain"]["input_model"] == "AnswerTarget"
    assert contract["answer_chain"]["output_model"] == "AnswerGenerationResult"
    assert contract["regeneration_chain"]["output_model"] == "AnswerGenerationResult"
    assert contract["retrieval"]["empty_evidence_policy"] == "human_review"
    assert contract["retrieval"]["evidence_required_fields"] == [
        "source_type",
        "source_id",
        "evidence_text",
        "relevance_score",
        "retrieval_rank",
    ]
    assert contract["safety"]["default_thresholds"]["factuality"] == 0.6
    assert contract["safety"]["action_to_ticket_status"] == {
        "ready_for_review": "drafted",
        "human_review": "human_review",
        "fixed_answer": "human_review",
    }
    assert contract["persistence"]["id_strategy"] == "locked_max_plus_one"
    assert contract["persistence"]["draft_evidence_safety_transaction"] is True
    assert contract["status"]["standard_ticket_statuses"] == ["open", "analyzed", "drafted", "human_review", "resolved"]
    assert contract["status"]["frontend_status_contract"]["drafted"] == {"review_status": "pending", "draft_status": "draft"}
    assert contract["regeneration"]["input"] == ["ticket_id", "regeneration_reason"]
    assert contract["regeneration"]["default_limit"] == 3
    assert contract["regeneration"]["evidence_policy"]["reuse_existing_evidence"] is True
    assert contract["regeneration"]["logs_admin_event"] is True
    assert contract["batch"]["dag_id"] == "cs_auto_answer_agent_daily"
    assert contract["batch"]["schedule_kst"] == "0 4 * * *"
    assert contract["batch"]["runs_after"] == "cs_auto_analysis_agent_daily"
    assert contract["batch"]["analysis_schedule_kst"] == "0 1 * * *"
    assert contract["batch"]["ticket_failure_policy"] == "log_and_continue"
    assert contract["batch"]["completion_event"] == "answer_batch_completed"
    assert contract["observability"]["log_table"] == "admin_event_logs"
    assert contract["observability"]["failed_queries_table"] == "not_used_for_answer_agent"
    assert contract["observability"]["allowed_metadata_fields"] == [
        "ticket_id",
        "analysis_id",
        "draft_id",
        "evidence_count",
        "safety_action",
        "failure_reason",
    ]
    assert contract["privacy_security"]["raw_query"] == "use_in_context_never_log_full_text"
    assert contract["privacy_security"]["transaction_id"] == "excluded_from_evidence_text"
    assert contract["privacy_security"]["refund_reason"] == "excluded_from_evidence_text"
    assert contract["implementation_priorities"] == [
        "1. keep test_answer_agent.py passing",
        "2. add ticket-level exception handling and batch logging",
        "3. improve answer draft quality",
        "4. strengthen safety/factuality validation",
        "5. keep draft/evidence/safety persistence transactional",
        "6. verify API/frontend status consistency",
        "7. add Airflow operation logs and failure recovery policy",
    ]
    assert contract["dependencies"]["chatbot_code"] is False


def test_fetch_answer_target_tickets_uses_operating_scope(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=()):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self, **kwargs):
            return FakeCursor()

    monkeypatch.delenv("CS_AUTO_ANSWER_BATCH_LIMIT", raising=False)
    monkeypatch.setenv("CS_AUTO_ANSWER_SOURCE_TYPE", "chatbot")
    monkeypatch.delenv("CS_AUTO_ANSWER_TERMINAL_STATUSES", raising=False)
    monkeypatch.setattr(agent, "db_connection", lambda: FakeConnection())

    assert agent.fetch_answer_target_tickets() == []

    sql = str(captured["sql"])
    params = captured["params"]
    assert "NOT EXISTS" in sql
    assert "FROM answer_draft" in sql
    assert "FROM final_response" in sql
    assert "ORDER BY ta.analyzed_at DESC NULLS LAST, ta.analysis_id DESC" in sql
    assert params == ("naver_cafe", ["resolved", "closed", "done", "cancelled", "canceled"], 30)


def test_process_answer_target_rejects_non_naver_cafe_source() -> None:
    try:
        agent.process_answer_target(_target(source_type="chatbot"))
    except ValueError as exc:
        assert "answer_generation_supports_naver_cafe_only" in str(exc)
    else:
        raise AssertionError("answer generation should only support naver_cafe source_type")


def test_answer_agent_contract_documents_roles_and_models() -> None:
    contract = agent.get_answer_agent_contract()

    assert contract["role_steps"] == [
        "fetch_analyzed_ticket",
        "collect_evidence",
        "generate_answer_draft",
        "save_answer_draft",
        "save_evidence_docs",
        "save_safety_results",
        "route_by_safety_result",
    ]
    assert contract["answer_chain"]["input_model"] == "AnswerTarget"
    assert contract["answer_chain"]["output_model"] == "AnswerGenerationResult"
    assert contract["regeneration_chain"]["output_model"] == "AnswerGenerationResult"
    assert contract["retrieval"]["empty_evidence_policy"] == "human_review"
    assert contract["retrieval"]["evidence_required_fields"] == [
        "source_type",
        "source_id",
        "evidence_text",
        "relevance_score",
        "retrieval_rank",
    ]
    assert contract["safety"]["default_thresholds"]["factuality"] == 0.6
    assert contract["safety"]["action_to_ticket_status"] == {
        "ready_for_review": "drafted",
        "human_review": "human_review",
        "fixed_answer": "human_review",
    }
    assert contract["persistence"]["id_strategy"] == "locked_max_plus_one"
    assert contract["persistence"]["draft_evidence_safety_transaction"] is True
    assert contract["status"]["standard_ticket_statuses"] == ["open", "analyzed", "drafted", "human_review", "resolved"]
    assert contract["status"]["frontend_status_contract"]["drafted"] == {"review_status": "pending", "draft_status": "draft"}
    assert contract["regeneration"]["input"] == ["ticket_id", "regeneration_reason"]
    assert contract["regeneration"]["default_limit"] == 3
    assert contract["regeneration"]["evidence_policy"]["reuse_existing_evidence"] is True
    assert contract["regeneration"]["logs_admin_event"] is True
    assert contract["batch"]["dag_id"] == "cs_auto_answer_agent_daily"
    assert contract["batch"]["schedule_kst"] == "0 4 * * *"
    assert contract["batch"]["runs_after"] == "cs_auto_analysis_agent_daily"
    assert contract["batch"]["analysis_schedule_kst"] == "0 1 * * *"
    assert contract["batch"]["ticket_failure_policy"] == "log_and_continue"
    assert contract["batch"]["completion_event"] == "answer_batch_completed"
    assert contract["observability"]["log_table"] == "admin_event_logs"
    assert contract["observability"]["failed_queries_table"] == "not_used_for_answer_agent"
    assert contract["observability"]["allowed_metadata_fields"] == [
        "ticket_id",
        "analysis_id",
        "draft_id",
        "evidence_count",
        "safety_action",
        "failure_reason",
    ]
    assert contract["privacy_security"]["raw_query"] == "use_in_context_never_log_full_text"
    assert contract["privacy_security"]["transaction_id"] == "excluded_from_evidence_text"
    assert contract["privacy_security"]["refund_reason"] == "excluded_from_evidence_text"
    assert contract["implementation_priorities"] == [
        "1. keep test_answer_agent.py passing",
        "2. add ticket-level exception handling and batch logging",
        "3. improve answer draft quality",
        "4. strengthen safety/factuality validation",
        "5. keep draft/evidence/safety persistence transactional",
        "6. verify API/frontend status consistency",
        "7. add Airflow operation logs and failure recovery policy",
    ]
    assert contract["dependencies"]["chatbot_code"] is False


def test_fetch_answer_target_tickets_uses_operating_scope(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=()):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self, **kwargs):
            return FakeCursor()

    monkeypatch.delenv("CS_AUTO_ANSWER_BATCH_LIMIT", raising=False)
    monkeypatch.setenv("CS_AUTO_ANSWER_SOURCE_TYPE", "chatbot")
    monkeypatch.delenv("CS_AUTO_ANSWER_TERMINAL_STATUSES", raising=False)
    monkeypatch.setattr(agent, "db_connection", lambda: FakeConnection())

    assert agent.fetch_answer_target_tickets() == []

    sql = str(captured["sql"])
    params = captured["params"]
    assert "NOT EXISTS" in sql
    assert "FROM answer_draft" in sql
    assert "FROM final_response" in sql
    assert "ORDER BY ta.analyzed_at DESC NULLS LAST, ta.analysis_id DESC" in sql
    assert params == ("naver_cafe", ["resolved", "closed", "done", "cancelled", "canceled"], 30)


def test_process_answer_target_rejects_non_naver_cafe_source() -> None:
    try:
        agent.process_answer_target(_target(source_type="chatbot"))
    except ValueError as exc:
        assert "answer_generation_supports_naver_cafe_only" in str(exc)
    else:
        raise AssertionError("answer generation should only support naver_cafe source_type")


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


def test_generate_answer_draft_text_falls_back_when_llm_fails(monkeypatch) -> None:
    logged: list[dict[str, object]] = []
    monkeypatch.setenv("CS_AUTO_LLM_DRAFT_ENABLED", "true")
    monkeypatch.setattr(agent, "invoke_structured_llm", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(agent, "log_answer_generation_event", lambda **kwargs: logged.append(kwargs))

    draft = agent.generate_answer_draft_text(_target(), _target(), _evidence())

    assert "안녕하세요. 게임 고객지원팀입니다." in draft
    assert "[payments] payment_status=paid" in draft
    assert logged[0]["event_type"] == "answer_llm_generation_failed"
    assert logged[0]["failure_reason"] == "llm_generation_failed"


def test_mask_sensitive_text_for_llm_prompt() -> None:
    masked = agent._mask_sensitive_text("email test@example.com UID:USER12345 transaction:TXN-ABCDEF123456")

    assert "test@example.com" not in masked
    assert "USER12345" not in masked
    assert "TXN-ABCDEF123456" not in masked
    assert "[email_masked]" in masked


def test_standardized_evidence_requires_text() -> None:
    invalid_evidence = [{"source_type": "payments", "source_id": "1", "evidence_text": ""}]
    try:
        agent.generate_answer_draft_text(_target(), _target(), invalid_evidence)
    except ValueError as exc:
        assert "EvidenceItem.evidence_text is required" in str(exc)
    else:
        raise AssertionError("invalid evidence should fail standardization")


def test_evaluate_answer_safety_routes_missing_evidence_to_human_review() -> None:
    result = agent.evaluate_answer_safety({"ticket_id": 1}, [])

    assert result["safety_action"] == "rejected"
    assert result["safety_reason"] == "missing_evidence"
    assert result["hallucination_score"] > result["factuality_score"]


def test_answer_chain_routes_zero_evidence_to_human_review(monkeypatch) -> None:
    monkeypatch.setattr(agent, "collect_answer_evidence", lambda ticket, analysis, strategy: [])

    result = agent.ANSWER_CHAIN.invoke(_target())

    assert result.context.evidence_docs == []
    assert result.safety.safety_action == "human_review"
    assert result.safety.safety_reason == "missing_evidence"


def test_evaluate_answer_safety_with_evidence_is_ready_for_review() -> None:
    result = agent.evaluate_answer_safety({"ticket_id": 1}, _evidence())

    assert result["safety_action"] == "approved"
    assert result["factuality_score"] == 0.9


def test_evaluate_answer_safety_routes_policy_risk_to_fixed_answer() -> None:
    result = agent.evaluate_answer_safety(
        {"ticket_id": 1},
        [
            {
                "source_type": "payments",
                "source_id": "1",
                "evidence_text": "무조건 환불",
                "relevance_score": 0.9,
                "retrieval_rank": 1,
            }
        ],
    )

    assert result["safety_action"] == "fixed_answer"
    assert result["safety_reason"] == "unsafe_expression_detected"
    assert result["policy_violation_score"] >= 0.5


def test_route_by_safety_result_updates_fixed_answer_status_and_analysis(monkeypatch) -> None:
    executed: list[tuple[str, tuple[object, ...]]] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=()):
            executed.append((" ".join(str(sql).split()), tuple(params)))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(agent, "db_connection", lambda: FakeConnection())

    agent.route_by_safety_result(
        {"ticket_id": 1},
        {"analysis_id": 100},
        {"draft_id": 55},
        {"safety_action": "fixed_answer"},
    )

    assert executed[0][1] == ("human_review", 1)
    assert "UPDATE qa_ticket" in executed[0][0]
    assert executed[1][1] == ("fixed_answer", 100)
    assert "UPDATE ticket_analysis" in executed[1][0]


def test_next_integer_id_rejects_unknown_table() -> None:
    class FakeCursor:
        def execute(self, sql, params=()):
            raise AssertionError("SQL should not execute for unsupported id target")

    try:
        agent._next_integer_id(FakeCursor(), "qa_ticket", "ticket_id")
    except ValueError as exc:
        assert "Unsupported id target" in str(exc)
    else:
        raise AssertionError("unsupported id target should fail")


def test_ticket_status_for_safety_action_matches_frontend_contract() -> None:
    assert agent._ticket_status_for_safety_action("ready_for_review") == "drafted"
    assert agent._ticket_status_for_safety_action("human_review") == "human_review"
    assert agent._ticket_status_for_safety_action("fixed_answer") == "human_review"
    assert agent._ticket_status_for_safety_action("unknown") == "human_review"


def test_stale_regeneration_evidence_routes_to_human_review() -> None:
    target = agent.AnswerTarget.model_validate(_target())
    context = agent.DraftContext(
        ticket=target,
        analysis=target,
        evidence_docs=[agent.EvidenceItem.model_validate(item) for item in _evidence()],
        regeneration_reason="다시 작성",
        evidence_is_stale=True,
    )

    result = agent._evaluate_context_safety(context)

    assert result.safety_action == "human_review"
    assert result.safety_reason == "stale_evidence_requires_review"


def test_regeneration_evidence_stale_policy_uses_draft_created_at(monkeypatch) -> None:
    monkeypatch.setenv("CS_AUTO_REGENERATION_EVIDENCE_MAX_AGE_DAYS", "7")

    assert agent._is_regeneration_evidence_stale(datetime.now() - timedelta(days=8)) is True
    assert agent._is_regeneration_evidence_stale(datetime.now() - timedelta(days=1)) is False
    assert agent._is_regeneration_evidence_stale(None) is True


def test_collect_answer_evidence_delegates_to_retrieval_router(monkeypatch) -> None:
    class FakeRouter:
        def retrieve_by_routing_target(self, ticket, analysis):
            return [{"source_type": analysis["routing_target"], "ticket_id": ticket["ticket_id"]}]

    monkeypatch.setattr(agent, "RetrievalRouter", lambda: FakeRouter())

    evidence = agent.collect_answer_evidence(_target(), _target(routing_target="DB_only"), {"routing_target": "DB_only"})

    assert evidence == [{"source_type": "DB_only", "ticket_id": 1}]


def test_generate_answer_result_builds_context_draft_and_safety(monkeypatch) -> None:
    monkeypatch.setattr(agent, "collect_answer_evidence", lambda ticket, analysis, strategy: _evidence())

    result = agent.generate_answer_result(_target())

    assert result.context.ticket.ticket_id == 1
    assert result.context.evidence_docs[0].source_type == "payments"
    assert result.safety.safety_action == "approved"
    assert "payment_status=paid" in result.draft_text


def test_generate_regeneration_result_uses_existing_context() -> None:
    context = {
        "ticket": _target(),
        "analysis": _target(),
        "evidence_docs": _evidence(),
    }

    result = agent.generate_regeneration_result(context, "간결하게")

    assert result.context.regeneration_reason == "간결하게"
    assert "재생성 요청 반영 사항" in result.draft_text


def test_process_answer_target_orchestrates_persistence(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(agent, "collect_answer_evidence", lambda ticket, analysis, strategy: _evidence())
    monkeypatch.setattr(
        agent,
        "persist_answer_generation_result",
        lambda result, route_ticket: calls.append(("persist", route_ticket, result.safety.safety_action))
        or {"draft": {"draft_id": 55}, "evidence_docs": [], "safety": {"safety_action": result.safety.safety_action}},
    )
    monkeypatch.setattr(agent, "log_answer_generation_event", lambda **kwargs: calls.append(("log", kwargs["event_type"])))

    agent.process_answer_target(_target())

    assert calls == [("draft", 1), ("evidence", 55), ("safety", 55), ("route", "approved")]
    assert calls == [
        ("log", "answer_generation_started"),
        ("persist", True, "ready_for_review"),
        ("log", "answer_generation_succeeded"),
    ]


def test_process_answer_target_logs_failure_without_sensitive_text(monkeypatch) -> None:
    logged: list[dict[str, object]] = []

    monkeypatch.setattr(agent, "collect_answer_evidence", lambda ticket, analysis, strategy: (_ for _ in ()).throw(RuntimeError("SQL failed raw text")))
    monkeypatch.setattr(agent, "log_answer_generation_event", lambda **kwargs: logged.append(kwargs))

    try:
        agent.process_answer_target(_target(raw_query="민감 원문", routing_target="DB_only"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("process_answer_target should re-raise failures")

    assert [row["event_type"] for row in logged] == ["answer_generation_started", "answer_generation_failed"]
    assert logged[-1]["failure_reason"] == "db_retrieval_failed"
    assert "민감 원문" not in str(logged)


def test_persist_answer_generation_result_saves_draft_evidence_safety_in_transaction(monkeypatch) -> None:
    executed: list[tuple[str, tuple[object, ...]]] = []
    next_ids = iter([55, 77, 88])

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=()):
            self.sql = " ".join(str(sql).split())
            self.params = tuple(params)
            executed.append((self.sql, self.params))

        def fetchone(self):
            if "SELECT COALESCE(MAX(" in self.sql:
                return {"next_id": next(next_ids)}
            if "RETURNING draft_id" in self.sql:
                return {"draft_id": 55, "ticket_id": 1, "analysis_id": 100, "draft_text": self.params[-1], "created_at": None}
            if "RETURNING evidence_id" in self.sql:
                return {
                    "evidence_id": 77,
                    "draft_id": 55,
                    "source_type": "payments",
                    "source_id": "1",
                    "evidence_text": "payment_status=paid",
                    "relevance_score": 0.9,
                    "retrieval_rank": 1,
                }
            if "RETURNING safety_id" in self.sql:
                return {"safety_id": 88, "draft_id": 55, "safety_action": "ready_for_review", "safety_reason": "ok", "retry_count": 0}
            raise AssertionError(f"unexpected fetchone after SQL: {self.sql}")

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self, **kwargs):
            return FakeCursor()

    target = agent.AnswerTarget.model_validate(_target())
    result = agent.AnswerGenerationResult(
        context=agent.DraftContext(
            ticket=target,
            analysis=target,
            evidence_docs=[agent.EvidenceItem.model_validate(item) for item in _evidence()],
        ),
        draft_text="draft",
        safety=agent.SafetyResult(
            hallucination_score=0.1,
            toxicity_score=0.0,
            policy_violation_score=0.0,
            factuality_score=0.9,
            safety_action="ready_for_review",
            safety_reason="ok",
        ),
    )
    monkeypatch.setattr(agent, "db_connection", lambda: FakeConnection())

    saved = agent.persist_answer_generation_result(result, route_ticket=True)

    assert saved["draft"]["draft_id"] == 55
    assert saved["evidence_docs"][0]["evidence_id"] == 77
    assert saved["safety"]["safety_id"] == 88
    assert any("INSERT INTO answer_draft" in sql for sql, _ in executed)
    assert any("INSERT INTO evidence_docs" in sql for sql, _ in executed)
    assert any("INSERT INTO safety_results" in sql for sql, _ in executed)
    assert executed[-1][1] == ("drafted", 1)


def test_run_answer_agent_logs_ticket_failures_and_continues(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    targets = [_target(ticket_id=11), _target(ticket_id=12), _target(ticket_id=13)]

    def fake_process(target: dict[str, object]) -> None:
        calls.append(("process", target["ticket_id"]))
        if target["ticket_id"] == 12:
            raise RuntimeError("retrieval failed")

    monkeypatch.setattr(agent, "fetch_answer_target_tickets", lambda: targets)
    monkeypatch.setattr(agent, "process_answer_target", fake_process)
    monkeypatch.setattr(agent, "log_answer_ticket_failure", lambda failure: calls.append(("failure", failure)))
    monkeypatch.setattr(agent, "log_answer_batch_event", lambda payload, status="success": calls.append(("batch", {**payload, "status": status})))

    result = agent.run_answer_agent()

    assert result["target_count"] == 3
    assert result["processed_count"] == 2
    assert result["failed_count"] == 1
    assert result["failures"][0]["ticket_id"] == 12
    assert result["failures"][0]["failure_reason"] == "answer_generation_failed"
    assert calls[0:3] == [("process", 11), ("process", 12), ("failure", result["failures"][0])]
    assert calls[3][0:2] == ("process", 13)
    assert calls[-1][0] == "batch"
    assert calls[-1][1]["status"] == "partial_failed"


def test_regenerate_agent_respects_limit_and_saves_new_draft(monkeypatch) -> None:
    monkeypatch.setattr(agent, "validate_regeneration_limit", lambda ticket_id: {"can_regenerate": True, "retry_count": 1})
    monkeypatch.setattr(agent, "fetch_regeneration_context", lambda ticket_id: {"ticket": _target(), "analysis": _target(), "evidence_docs": _evidence()})
    monkeypatch.setattr(
        agent,
        "persist_answer_generation_result",
        lambda result, route_ticket: {
            "draft": {"draft_id": 77, "ticket_id": result.context.ticket.ticket_id},
            "evidence_docs": [item.model_dump() for item in result.context.evidence_docs],
            "safety": {"retry_count": result.safety.retry_count},
        },
    )
    logged: list[dict[str, object]] = []
    monkeypatch.setattr(agent, "log_regeneration_event", lambda **kwargs: logged.append(kwargs))

    result = agent.regenerate_agent(1, "정중하게")

    assert result is not None
    assert result["draft"]["draft_id"] == 77
    assert result["retry_count"] == 2
    assert result["safety"]["retry_count"] == 2
    assert logged[0]["ticket_id"] == 1
    assert logged[0]["retry_count"] == 2


def test_regenerate_agent_returns_none_when_limit_exceeded(monkeypatch) -> None:
    monkeypatch.setattr(agent, "validate_regeneration_limit", lambda ticket_id: {"can_regenerate": False, "retry_count": 3, "limit": 3})
    monkeypatch.setattr(agent, "fetch_regeneration_context", lambda ticket_id: (_ for _ in ()).throw(AssertionError("should not fetch context")))

    assert agent.regenerate_agent(1, "다시 작성") is None



