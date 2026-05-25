from __future__ import annotations

from chatbot.tools import registry


def _tool_names(tools: list) -> set[str]:
    return {tool.name for tool in tools}


def test_payment_tools_include_required_operation_reads() -> None:
    assert _tool_names(registry.PAYMENT_TOOLS) == {
        "read_payments",
        "read_refunds",
        "read_item_delivery_logs",
    }


def test_bug_tools_include_gameplay_operation_reads() -> None:
    assert _tool_names(registry.BUG_TOOLS) == {
        "read_gacha_logs",
        "read_item_delivery_logs",
    }


def test_faq_tools_are_empty_because_faq_rag_is_functional_pipeline() -> None:
    assert registry.FAQ_TOOLS == []
