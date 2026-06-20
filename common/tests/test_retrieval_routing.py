from __future__ import annotations

from common.retrieval.routing import (
    require_state_route,
    route_after_retry_limit,
    route_after_safety,
    route_by_mapping,
    state_value,
)


class DummyState:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_state_value_supports_mapping_and_objects() -> None:
    assert state_value({"category": "FAQ"}, "category") == "FAQ"
    assert state_value(DummyState(category="FAQ"), "category") == "FAQ"


def test_route_by_mapping_uses_default_for_unknown_values() -> None:
    route_map = {"FAQ": "faq_agent", "VOC": "voc_agent"}

    assert route_by_mapping({"category": "FAQ"}, field_name="category", route_map=route_map, default_route="voc_agent") == "faq_agent"
    assert route_by_mapping({"category": "unknown"}, field_name="category", route_map=route_map, default_route="voc_agent") == "voc_agent"


def test_require_state_route_uses_fallback_fields() -> None:
    state = DummyState(target_route=None)
    state.analysis = DummyState(target_route="rag_reply")

    assert (
        require_state_route(state.analysis, field_names=("target_route",), allowed_values=("rag_reply", "urgent_alert"), route_name="target_route")
        == "rag_reply"
    )


def test_route_after_retry_limit_stops_after_max_retries() -> None:
    assert (
        route_after_retry_limit(
            {"retry_count": 3, "max_retries": 3},
            retry_route="query_router",
            exhausted_route="urgent_alert_node",
        )
        == "urgent_alert_node"
    )


def test_route_after_safety_returns_retry_then_final_then_category() -> None:
    category_router = lambda state: route_by_mapping(
        state,
        field_name="category",
        route_map={"FAQ": "faq_agent"},
        default_route="voc_agent",
    )

    assert (
        route_after_safety(
            {"category": "FAQ", "safety_action": "MASKING", "retry_count": 1},
            category_router=category_router,
            max_masking_retry=2,
            max_safety_retry=2,
            retry_node="draft_persistence",
            final_node="final_response",
        )
        == "draft_persistence"
    )
    assert (
        route_after_safety(
            {"category": "FAQ", "safety_action": "SAFE_FALLBACK", "retry_count": 0},
            category_router=category_router,
            max_masking_retry=2,
            max_safety_retry=2,
            retry_node="draft_persistence",
            final_node="final_response",
        )
        == "final_response"
    )
    assert (
        route_after_safety(
            {"category": "FAQ", "safety_action": None, "retry_count": 0, "safety_passed": False},
            category_router=category_router,
            max_masking_retry=2,
            max_safety_retry=2,
            retry_node="draft_persistence",
            final_node="final_response",
        )
        == "faq_agent"
    )
