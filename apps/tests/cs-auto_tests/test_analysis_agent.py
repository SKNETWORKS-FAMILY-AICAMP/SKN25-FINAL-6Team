from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[3]
os.environ.setdefault("CS_AUTO_KEYWORD_DIR", str(ROOT_DIR / "data" / "keywords"))
os.environ.setdefault("CS_AUTO_PROMPT_DIR", str(ROOT_DIR / "data" / "prompts" / "cs_auto"))
for path in reversed(
    [
        ROOT_DIR,
        ROOT_DIR / "apps" / "cs_auto" / "backend",
    ]
):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from agents import analysis_agent as agent  # noqa: E402


# 테스트에서 반복해서 쓰는 qa_ticket 기본 샘플을 만든다.
def _ticket(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticket_id": 11,
        "account_id": 101,
        "user_id": 1001,
        "title": "결제 상품 미지급",
        "raw_query": "결제했는데 상품이 지급되지 않았습니다. 빨리 확인해주세요.",
        "source_type": "naver_cafe",
        "status": "open",
        "session_id": None,
    }
    payload.update(overrides)
    return payload


# 키워드 분석 결과와 라우팅 결과가 최종 AnalysisResult에 들어가는지 확인한다.
def test_build_analysis_result_classifies_scores_and_adds_routing_target(monkeypatch) -> None:
    def fake_add_routing_target(parts: dict[str, object]) -> dict[str, object]:
        assert parts["category"] == "payment"
        assert parts["sentiment"] == "negative"
        assert parts["risk_level"] == "HIGH"
        return {**parts, "routing_target": "DB&DOC"}

    monkeypatch.setattr(agent, "_add_routing_target", fake_add_routing_target)

    result = agent.build_analysis_result(_ticket())

    assert result.ticket_id == 11
    assert result.category == "payment"
    assert result.sentiment == "negative"
    assert result.risk_level == "HIGH"
    assert result.routing_target == "DB&DOC"
    assert "결제 상품 미지급" in result.enriched_query
    assert "응답 근거는 DB&DOC" in result.summary


# chatbot 문의처럼 routing_target이 None인 분석 결과도 dict로 정상 반환되는지 확인한다.
def test_analyze_ticket_returns_dict_with_null_routing_target_for_chatbot(monkeypatch) -> None:
    monkeypatch.setattr(
        agent,
        "_add_routing_target",
        lambda parts: {**parts, "routing_target": None},
    )

    result = agent.analyze_ticket(
        _ticket(
            ticket_id=12,
            title="간단 문의",
            raw_query="안녕하세요",
            source_type="chatbot",
        )
    )

    assert result["ticket_id"] == 12
    assert result["category"] == "general"
    assert result["risk_level"] == "LOW"
    assert result["routing_target"] is None
    assert "chatbot 문의는 분석 단계에서 별도 응답 근거 경로를 생성하지 않습니다" in result["summary"]


# Airflow가 호출하는 배치 함수가 조회, 분석, 저장, 완료 표시 순서로 동작하는지 확인한다.
def test_run_analysis_agent_fetches_and_saves(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    tickets = [_ticket(ticket_id=21), _ticket(ticket_id=22)]

    monkeypatch.setattr(agent, "fetch_unanalyzed_tickets", lambda: tickets)
    monkeypatch.setattr(
        agent,
        "analyze_ticket",
        lambda ticket: calls.append(("analyze", int(ticket["ticket_id"]))) or {"ticket_id": ticket["ticket_id"]},
    )
    monkeypatch.setattr(
        agent,
        "save_ticket_analysis",
        lambda analysis: calls.append(("save", int(analysis["ticket_id"]))) or {"ticket_id": analysis["ticket_id"]},
    )
    agent.run_analysis_agent()

    assert calls == [
        ("analyze", 21),
        ("save", 21),
        ("analyze", 22),
        ("save", 22),
    ]


def test_score_risk_high_keyword_takes_priority(monkeypatch) -> None:
    monkeypatch.setattr(agent, "HIGH_RISK_KEYWORDS", ("lawsuit",))
    monkeypatch.setattr(agent, "NEGATIVE_KEYWORDS", ())
    monkeypatch.setattr(agent, "ROUTING_STATUS_LOOKUP_KEYWORDS", ())
    monkeypatch.setattr(agent, "ROUTING_SANCTION_OR_EXCEPTION_KEYWORDS", ())
    monkeypatch.setitem(agent.CATEGORY_KEYWORDS, "account", ("login",))

    enriched = agent._build_enriched_ticket(
        agent._to_ticket_payload(_ticket(title="general inquiry", raw_query="lawsuit over this charge"))
    )

    assert agent._score_risk(enriched, "account") == "HIGH"


def test_score_risk_account_defaults_to_mid_without_escalation_signals(monkeypatch) -> None:
    monkeypatch.setattr(agent, "HIGH_RISK_KEYWORDS", ())
    monkeypatch.setattr(agent, "NEGATIVE_KEYWORDS", ("angry",))
    monkeypatch.setattr(agent, "ROUTING_STATUS_LOOKUP_KEYWORDS", ("status",))
    monkeypatch.setattr(agent, "ROUTING_SANCTION_OR_EXCEPTION_KEYWORDS", ("ban",))
    monkeypatch.setitem(agent.CATEGORY_KEYWORDS, "account", ("login", "password"))

    enriched = agent._build_enriched_ticket(
        agent._to_ticket_payload(_ticket(title="login help", raw_query="I cannot find the password reset page"))
    )

    assert agent._score_risk(enriched, "account") == "MID"


def test_score_risk_account_escalates_with_uid_and_status_lookup(monkeypatch) -> None:
    monkeypatch.setattr(agent, "HIGH_RISK_KEYWORDS", ())
    monkeypatch.setattr(agent, "NEGATIVE_KEYWORDS", ())
    monkeypatch.setattr(agent, "ROUTING_STATUS_LOOKUP_KEYWORDS", ("status",))
    monkeypatch.setattr(agent, "ROUTING_SANCTION_OR_EXCEPTION_KEYWORDS", ())
    monkeypatch.setitem(agent.CATEGORY_KEYWORDS, "account", ("account",))

    enriched = agent._build_enriched_ticket(
        agent._to_ticket_payload(_ticket(title="account issue", raw_query="uid 12345678 account status check please"))
    )

    assert agent._score_risk(enriched, "account") == "HIGH"


def test_score_risk_general_escalates_to_mid_on_repeated_negative_status_signals(monkeypatch) -> None:
    monkeypatch.setattr(agent, "HIGH_RISK_KEYWORDS", ())
    monkeypatch.setattr(agent, "NEGATIVE_KEYWORDS", ("angry", "frustrated"))
    monkeypatch.setattr(agent, "ROUTING_STATUS_LOOKUP_KEYWORDS", ("status",))
    monkeypatch.setattr(agent, "ROUTING_SANCTION_OR_EXCEPTION_KEYWORDS", ())

    enriched = agent._build_enriched_ticket(
        agent._to_ticket_payload(
            _ticket(title="need help", raw_query="angry and frustrated about uid 12345678 status update")
        )
    )

    assert agent._score_risk(enriched, "general") == "MID"


# 직접 실행할 때 루트 .env에 있는 LLM 설정을 읽어 실제 라우팅 LLM 호출이 가능하게 한다.
def _load_root_env() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# 긴 JSON 객체를 터미널에서 읽기 쉽게 출력한다.
def _print_json(title: str, payload: object) -> None:
    print(f"\n[{title}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# 입력받은 qa_ticket이 분석 파이프라인에서 어떤 중간값으로 바뀌는지 단계별로 보여준다.
def _analyze_ticket_step_by_step(ticket: dict[str, object]) -> dict[str, object]:
    _print_json("1. 입력 qa_ticket", ticket)

    ticket_payload = agent._to_ticket_payload(ticket)
    _print_json("2. TicketPayload 검증 결과", ticket_payload.model_dump())

    enriched = agent._build_enriched_ticket(ticket_payload)
    _print_json(
        "3. EnrichedTicket 생성 결과",
        {
            "ticket_id": enriched.ticket.ticket_id,
            "enriched_query": enriched.enriched_query,
            "normalized_query": enriched.normalized_query,
        },
    )

    category = agent._classify_category(enriched)
    print(f"\n[4. 카테고리 분류 결과]\n{category}")

    sentiment = agent._score_sentiment(enriched)
    print(f"\n[5. 감성 분석 결과]\n{sentiment}")

    risk_level = agent._score_risk(enriched, category)
    print(f"\n[6. 위험도 분석 결과]\n{risk_level}")

    routing_input = {
        "enriched": enriched,
        "category": category,
        "sentiment": sentiment,
        "risk_level": risk_level,
    }
    _print_json("7. routing_target 판단 입력", agent._build_routing_prompt_input(routing_input))

    routed = agent._add_routing_target(routing_input)
    print(f"\n[8. routing_target 판단 결과]\n{routed['routing_target']}")

    result = agent.AnalysisResult(
        ticket_id=enriched.ticket.ticket_id,
        category=category,
        enriched_query=enriched.enriched_query,
        risk_level=risk_level,
        sentiment=sentiment,
        routing_target=routed["routing_target"],
        summary=agent._summarize(enriched, category, routed["routing_target"], sentiment, risk_level),
    ).model_dump()
    _print_json("9. 최종 analysis", result)
    return result


# 터미널에서 qa_ticket JSON을 입력받아 실제 analysis_agent 분석 결과를 출력한다.
def _manual_analyze_ticket_with_input() -> None:
    _load_root_env()
    if not os.environ.get("LLM_API_KEY") or not os.environ.get("LLM_MODEL"):
        raise RuntimeError("루트 .env 또는 실행 환경에 LLM_API_KEY, LLM_MODEL이 있어야 실제 analysis를 실행할 수 있다.")

    raw_ticket = input("qa_ticket JSON: ").strip()
    if not raw_ticket:
        raise ValueError("qa_ticket JSON을 입력해야 한다.")
    ticket = json.loads(raw_ticket)

    result = _analyze_ticket_step_by_step(ticket)

    assert result["ticket_id"] == ticket["ticket_id"]
    assert result["category"] in {"payment", "refund", "account", "bug", "gacha", "policy", "general"}
    assert result["sentiment"] in {"positive", "neutral", "negative"}
    assert result["risk_level"] in {"LOW", "MID", "HIGH"}
    assert result["routing_target"] in {"DB_only", "doc_only", "DB&DOC", "fixed_answer", None}


# pytest로 실행할 때는 -s 옵션이 있는 수동 실행에서만 input을 받는다.
def test_manual_analyze_ticket_with_input() -> None:
    r"""input으로 받은 qa_ticket JSON을 분석 파이프라인에 태워 확인한다.

    실행 예:
    python apps\tests\cs-auto_tests\test_analysis_agent.py
    또는
    python -m pytest apps\tests\cs-auto_tests\test_analysis_agent.py -s
    """

    if not sys.stdin.isatty():
        pytest.skip("-s 옵션 또는 python 직접 실행으로 input을 받을 때만 수동 테스트를 실행한다.")

    try:
        _manual_analyze_ticket_with_input()
    except Exception as exc:
        pytest.fail(str(exc))


# pytest 없이 `python test_analysis_agent.py`로 실행해도 input 실험을 할 수 있게 한다.
if __name__ == "__main__":
    _manual_analyze_ticket_with_input()
