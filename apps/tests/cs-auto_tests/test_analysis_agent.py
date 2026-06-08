from __future__ import annotations

from agents import analysis_agent as agent


def _ticket(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticket_id": 1,
        "account_id": 10,
        "user_id": 20,
        "title": "결제 상품 미지급",
        "raw_query": "패키지를 구매했는데 상품이 지급되지 않았습니다.",
        "source_type": "naver_cafe",
        "status": "open",
        "responder_type": "agent",
    }
    payload.update(overrides)
    return payload


def test_build_enriched_query_combines_title_and_body() -> None:
    enriched = agent.build_enriched_query(_ticket(title="  결제\n문의  ", raw_query="상품   미지급"))

    assert enriched == "결제 문의 상품 미지급"


def test_classify_sentiment_risk_and_routing_helpers() -> None:
    ticket = _ticket(title="환불 문의", raw_query="환불 거부하면 신고하겠습니다.")
    enriched = agent.build_enriched_query(ticket)

    assert agent.classify_ticket_category(ticket, enriched) == "refund"
    assert agent.score_sentiment(ticket, enriched) == "negative"
    assert agent.score_risk_level(ticket, enriched, "refund") == "HIGH"
    assert agent.decide_routing_target(ticket, "refund", enriched) == "DB&DOC"


def test_policy_or_bug_routes_to_documents_only() -> None:
    ticket = _ticket(title="공지 오류 문의", raw_query="게임 접속 오류가 있습니다.")
    enriched = agent.build_enriched_query(ticket)

    assert agent.classify_ticket_category(ticket, enriched) == "bug"
    assert agent.decide_routing_target(ticket, "bug", enriched) == "doc_only"


def test_non_cafe_ticket_routes_to_human_review() -> None:
    ticket = _ticket(source_type="email", raw_query="로그인이 안 됩니다.")
    enriched = agent.build_enriched_query(ticket)

    assert agent.decide_routing_target(ticket, "account", enriched) == "human_review"


def test_analyze_ticket_chain_returns_saveable_payload() -> None:
    result = agent.analyze_ticket(_ticket())

    assert result["ticket_id"] == 1
    assert result["category"] == "payment"
    assert result["routing_target"] == "DB&DOC"
    assert "payment" in result["summary"]


def test_build_ticket_analysis_payload_validates_shape() -> None:
    payload = agent.build_ticket_analysis_payload(
        _ticket(),
        "결제 상품 미지급",
        "payment",
        "DB&DOC",
        "neutral",
        "MID",
        "summary",
    )

    assert payload == {
        "ticket_id": 1,
        "category": "payment",
        "responder_type": "agent",
        "enriched_query": "결제 상품 미지급",
        "risk_level": "MID",
        "sentiment": "neutral",
        "routing_target": "DB&DOC",
        "summary": "summary",
    }


def test_run_analysis_agent_orchestrates_batch(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(agent, "fetch_unanalyzed_tickets", lambda: [_ticket(ticket_id=11), _ticket(ticket_id=12)])
    monkeypatch.setattr(
        agent,
        "analyze_ticket",
        lambda ticket: calls.append(("analyze", ticket["ticket_id"])) or {"ticket_id": ticket["ticket_id"]},
    )
    monkeypatch.setattr(
        agent,
        "save_ticket_analysis",
        lambda payload: calls.append(("save", payload["ticket_id"]))
        or {"ticket_id": payload["ticket_id"], "analysis_id": int(payload["ticket_id"]) + 100},
    )
    monkeypatch.setattr(
        agent,
        "mark_ticket_analysis_completed",
        lambda ticket_id, analysis_id: calls.append(("mark", (ticket_id, analysis_id))),
    )
    monkeypatch.setattr(agent, "log_analysis_batch_event", lambda payload: calls.append(("log", payload)))

    agent.run_analysis_agent()

    assert calls == [
        ("analyze", 11),
        ("save", 11),
        ("mark", (11, 111)),
        ("analyze", 12),
        ("save", 12),
        ("mark", (12, 112)),
        ("log", {"target_count": 2, "processed_count": 2}),
    ]
