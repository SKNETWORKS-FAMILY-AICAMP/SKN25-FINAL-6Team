from __future__ import annotations

from chatbot.generation import payment_agent
from chatbot.repository import operation_log_repository


def test_payment_agent_collects_context_by_logged_in_user(monkeypatch) -> None:
    captured = {}

    payment_context = {
        "status": "ok",
        "user_id": 1,
        "account_id": 101,
        "data": {
            "accounts": [{"account_id": 101, "user_id": 1}],
            "payments": [{"payment_id": 201, "account_id": 101, "payment_status": "paid"}],
            "refunds": [],
            "item_delivery_logs": [{"delivery_id": 301, "account_id": 101, "delivery_status": "pending"}],
            "gacha_logs": [],
        },
        "counts": {"payments": 1, "item_delivery_logs": 1},
        "count": 2,
    }

    def fake_collect_payment_context_by_user(*, user_id, account_id=None, query_text=None):
        captured["collector_args"] = (user_id, account_id, query_text)
        return payment_context

    monkeypatch.setattr(payment_agent, "collect_payment_context_by_user", fake_collect_payment_context_by_user)

    def fake_invoke_payment_agent(state):
        captured["agent_state"] = state
        return {"messages": [{"role": "assistant", "content": "결제 내역과 지급 로그를 확인했습니다."}]}

    monkeypatch.setattr(payment_agent, "invoke_payment_agent", fake_invoke_payment_agent)

    result = payment_agent.payment_agent_node(
        {
            "ticket_id": 1,
            "session_id": 1,
            "user_id": 1,
            "account_id": 101,
            "raw_query": "결제했는데 상품이 안 들어왔어요",
            "normalized_query": "결제했는데 상품이 안 들어왔어요",
            "messages": [{"role": "user", "content": "결제했는데 상품이 안 들어왔어요"}],
            "category": "결제",
            "routing_target": "payment_agent",
            "retry_count": 0,
        }
    )

    assert captured["collector_args"][0:2] == (1, 101)
    assert "결제했는데 상품이 안 들어왔어요" in captured["collector_args"][2]
    assert captured["agent_state"]["payment_context"]["status"] == "ok"
    assert captured["agent_state"]["payment_context"]["data"]["payments"] == payment_context["data"]["payments"]
    assert (
        captured["agent_state"]["payment_context"]["data"]["item_delivery_logs"]
        == payment_context["data"]["item_delivery_logs"]
    )
    assert "Payment DB context scoped to the logged-in user_id only" in captured["agent_state"]["messages"][-1]["content"]
    assert result["payment_context"]["status"] == "ok"
    assert result["payment_context"]["data"]["payments"] == payment_context["data"]["payments"]
    assert result["payment_context"]["data"]["item_delivery_logs"] == payment_context["data"]["item_delivery_logs"]
    assert {doc["source_type"] for doc in result["retrieved_documents"]} == {"payments", "item_delivery_logs"}
    assert result["draft_text"] == "결제 내역과 지급 로그를 확인했습니다."


def test_payment_agent_does_not_collect_without_user_id(monkeypatch) -> None:
    def fail_collect(*args, **kwargs):
        raise AssertionError("collector should not run without user_id")

    monkeypatch.setattr(payment_agent, "collect_payment_context_by_user", fail_collect)
    monkeypatch.setattr(
        payment_agent,
        "invoke_payment_agent",
        lambda state: {"messages": [{"role": "assistant", "content": "로그인이 필요합니다."}]},
    )

    result = payment_agent.payment_agent_node(
        {
            "ticket_id": 1,
            "session_id": 1,
            "account_id": None,
            "messages": [{"role": "user", "content": "결제 내역 확인"}],
            "category": "결제",
            "routing_target": "payment_agent",
            "retry_count": 0,
        }
    )

    assert result["payment_context"]["status"] == "skipped"
    assert result["payment_context"]["reason"] == "missing_user_id"
    assert result["retrieved_documents"] == []


def test_collect_payment_context_queries_are_scoped_by_user_and_optional_account(monkeypatch) -> None:
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params):
            calls.append((sql, params))

        def fetchall(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, row_factory=None):
            return FakeCursor()

    monkeypatch.setattr(operation_log_repository, "_db_context", lambda: (lambda: FakeConnection(), object()))

    result = operation_log_repository.collect_payment_context_by_user(user_id=7, account_id=99)

    assert result["status"] == "ok"
    assert len(calls) == 2
    assert all("a.user_id = %s" in sql for sql, _ in calls)
    assert calls[0][1] == (7, 99, 99, operation_log_repository.PAYMENT_CONTEXT_LIMIT)
    evidence_sql, evidence_params = calls[1]
    assert evidence_params[:12] == (7, 99, 99, 7, 99, 99, 7, 99, 99, 7, 99, 99)
    assert "FROM payments p" in evidence_sql and "JOIN game_accounts a" in evidence_sql
    assert "FROM refunds r" in evidence_sql and "JOIN game_accounts a" in evidence_sql
    assert "FROM item_delivery_logs d" in evidence_sql and "JOIN game_accounts a" in evidence_sql
    assert "FROM gacha_logs g" in evidence_sql and "JOIN game_accounts a" in evidence_sql
