from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
os.environ.setdefault("CS_AUTO_SQL_DIR", str(ROOT_DIR / "data" / "sql"))

for path in reversed(
    [
        ROOT_DIR / "apps" / "cs_auto" / "backend",
        ROOT_DIR / "packages" / "common-python" / "src",
    ]
):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from agents.tool.dbsearch import DbSearchRouter, TextToSqlPlan, TextToSqlFilter, build_operation_schema_context, render_text_to_sql  # noqa: E402


def test_db_router_uses_default_query_type_by_category() -> None:
    router = DbSearchRouter()

    account_decision = router.decide_query_type({}, {"category": "account", "enriched_query": "비밀번호를 바꾸고 싶어요"})
    refund_decision = router.decide_query_type({}, {"category": "refund", "enriched_query": "환불 상태를 확인하고 싶어요"})
    payment_decision = router.decide_query_type({}, {"category": "payment", "enriched_query": "결제가 안 돼요"})
    gacha_decision = router.decide_query_type({}, {"category": "gacha", "enriched_query": "뽑기 기록이 이상해요"})

    assert account_decision.query_type == "fixed_sql"
    assert refund_decision.query_type == "fixed_sql"
    assert payment_decision.query_type == "text_to_sql"
    assert gacha_decision.query_type == "text_to_sql"


def test_render_text_to_sql_adds_multi_hop_join_for_ticket_filters() -> None:
    schema_context = build_operation_schema_context("payment")
    plan = TextToSqlPlan(
        tables=["payments"],
        columns=["payments.payment_id", "qa_ticket.ticket_id"],
        filters=[
            TextToSqlFilter(
                column="qa_ticket.ticket_id",
                operator="=",
                value_source="ticket.ticket_id",
            )
        ],
        limit=5,
    )

    sql, params = render_text_to_sql(
        plan,
        ticket={"ticket_id": 8000, "account_id": 1234, "user_id": 5678},
        schema_context=schema_context,
    )

    assert "FROM payments" in sql
    assert "JOIN game_accounts ON payments.account_id = game_accounts.account_id" in sql
    assert "JOIN qa_ticket ON game_accounts.account_id = qa_ticket.account_id" in sql
    assert "WHERE payments.account_id = %s AND qa_ticket.ticket_id = %s" in sql
    assert params == (1234, 8000, 5)


def test_render_text_to_sql_injects_account_scope_when_required() -> None:
    schema_context = build_operation_schema_context("payment")
    plan = TextToSqlPlan(
        tables=["payments"],
        columns=["payments.payment_id", "payments.payment_status"],
        filters=[
            TextToSqlFilter(
                column="payments.payment_status",
                operator="=",
                value_source="literal",
                value="fail",
            )
        ],
        limit=5,
        needs_account_scope=True,
    )

    sql, params = render_text_to_sql(
        plan,
        ticket={"ticket_id": 1, "account_id": 107, "user_id": 7},
        schema_context=schema_context,
    )

    assert "WHERE payments.account_id = %s AND payments.payment_status = %s" in sql
    assert params == (107, "fail", 5)


def test_render_text_to_sql_drops_overfit_payment_literals_for_generic_diagnosis() -> None:
    schema_context = build_operation_schema_context("payment")
    plan = TextToSqlPlan(
        tables=["payments"],
        columns=["payments.payment_id", "payments.payment_status"],
        filters=[
            TextToSqlFilter(
                column="payments.payment_status",
                operator="=",
                value_source="literal",
                value="fail",
            )
        ],
        limit=5,
        needs_account_scope=True,
    )

    sql, params = render_text_to_sql(
        plan,
        ticket={"ticket_id": 1, "account_id": 107, "user_id": 7},
        schema_context=schema_context,
        question="지금 결제가 안 돼요",
    )

    assert "payments.payment_status = %s" not in sql
    assert "WHERE payments.account_id = %s" in sql
    assert params == (107, 5)


def test_render_text_to_sql_uses_left_join_for_refunds() -> None:
    schema_context = build_operation_schema_context("refund")
    plan = TextToSqlPlan(
        tables=["payments"],
        columns=["payments.payment_id", "refunds.refund_status"],
        joins=[{"left": "payments.payment_id", "right": "refunds.payment_id"}],
        limit=5,
    )

    sql, _ = render_text_to_sql(
        plan,
        ticket={"ticket_id": 1, "account_id": 107, "user_id": 7},
        schema_context=schema_context,
    )

    assert "LEFT JOIN refunds ON payments.payment_id = refunds.payment_id" in sql


def test_render_text_to_sql_drops_overfit_gacha_literal_filters() -> None:
    schema_context = build_operation_schema_context("gacha")
    plan = TextToSqlPlan(
        tables=["gacha_logs"],
        columns=["gacha_logs.gacha_id", "gacha_logs.banner_name", "gacha_logs.rarity"],
        filters=[
            TextToSqlFilter(
                column="gacha_logs.banner_name",
                operator="=",
                value_source="literal",
                value="캐릭터 이벤트 기원",
            ),
            TextToSqlFilter(
                column="gacha_logs.rarity",
                operator="=",
                value_source="literal",
                value="5성",
            ),
        ],
        limit=5,
        needs_account_scope=True,
    )

    sql, params = render_text_to_sql(
        plan,
        ticket={"ticket_id": 1, "account_id": 3344, "user_id": 3244},
        schema_context=schema_context,
        question="천장인데 픽뚫이 나와서 확률이 이상합니다.",
    )

    assert "gacha_logs.banner_name = %s" not in sql
    assert "gacha_logs.rarity = %s" not in sql
    assert "WHERE gacha_logs.account_id = %s" in sql
    assert params == (3344, 5)
