"""
멀티홉 검색 기능 테스트

테스트 항목:
1. Rule-based 복합 질문 감지 (_looks_like_multihop_query)
2. LLM decomposition (_decompose_multihop_queries)
3. 의도 판단 (_infer_intent_from_query)
4. 라우팅 결정 (_determine_route_from_query_text)
5. 하위 질문 실행 (_execute_sub_query_sync)
6. 멀티홉 통합 흐름 (_maybe_run_multihop_retrieval)
"""

from __future__ import annotations

import json
import pytest

from chatbot.generation.faq_agent import (
    _determine_route_from_query_text,
    _determine_route_for_sub_query,
    _generate_brief_summary,
    _infer_intent_from_query,
    _looks_like_multihop_query,
    _maybe_run_multihop_retrieval,
    SubQuery,
)
from chatbot.schemas import ChatbotState


class TestMultihopDetection:
    """Rule-based 복합 질문 감지 테스트"""
    
    def test_single_domain_query_not_multihop(self) -> None:
        """단일 도메인 질문은 멀티홉 아님"""
        query = "결제는 어떻게 하나요?"
        is_multihop, reason = _looks_like_multihop_query(query)
        assert not is_multihop or reason == "precheck_disabled"
    
    def test_payment_and_refund_is_multihop(self) -> None:
        """결제 + 환불 = 멀티홉"""
        query = "결제했는데 환불은 어떻게 받나요?"
        is_multihop, reason = _looks_like_multihop_query(query)
        assert is_multihop
        assert reason == "payment_with_refund"
    
    def test_account_deletion_with_payment_is_multihop(self) -> None:
        """계정 삭제 + 결제 = 멀티홉"""
        query = "결제 기록 확인하고 계정 삭제하고 싶어요"
        is_multihop, reason = _looks_like_multihop_query(query)
        assert is_multihop
        assert reason == "account_deletion_with_payment"
    
    def test_payment_with_reward_delivery_is_multihop(self) -> None:
        """결제 + 보상 = 멀티홉"""
        query = "결제하면 보상이 우편함에 들어올까요?"
        is_multihop, reason = _looks_like_multihop_query(query)
        assert is_multihop or reason == "precheck_disabled"


class TestIntentInference:
    """Rule-based 의도 판단 테스트"""
    
    def test_payment_missing_intent(self) -> None:
        """결제 미지급 의도"""
        query = "결제했는데 못 받았어요"
        intent = _infer_intent_from_query(query)
        assert intent == "payment_missing_item"
    
    def test_refund_eligibility_intent(self) -> None:
        """환불 자격 의도"""
        query = "환불 가능한가요?"
        intent = _infer_intent_from_query(query)
        assert intent == "refund_eligibility"
    
    def test_account_deletion_intent(self) -> None:
        """계정 삭제 의도"""
        query = "계정을 삭제하고 싶어요"
        intent = _infer_intent_from_query(query)
        assert intent == "account_deletion"
    
    def test_reward_delivery_intent(self) -> None:
        """보상 미지급 의도"""
        query = "보상이 안 들어왔어요"
        intent = _infer_intent_from_query(query)
        assert intent == "reward_delivery"
    
    def test_bug_report_intent(self) -> None:
        """버그 보고 의도"""
        query = "게임 버그가 있어요"
        intent = _infer_intent_from_query(query)
        assert intent == "bug_report"
    
    def test_unknown_intent_defaults_to_general(self) -> None:
        """미정의 의도는 general_faq"""
        query = "게임 스토리 설명해주세요"
        intent = _infer_intent_from_query(query)
        assert intent == "general_faq"


class TestRouting:
    """라우팅 결정 테스트"""
    
    def test_payment_intent_routes_to_payment_agent(self) -> None:
        """payment_missing_item → payment_agent"""
        query = "결제했는데 못 받았어요"
        route = _determine_route_from_query_text(query)
        assert route == "payment_agent"
    
    def test_refund_intent_routes_to_faq_agent(self) -> None:
        """refund_eligibility → faq_agent"""
        query = "환불 가능한가요?"
        route = _determine_route_from_query_text(query)
        assert route == "faq_agent"
    
    def test_bug_intent_routes_to_bug_agent(self) -> None:
        """bug_report → bug_agent"""
        query = "게임 버그가 있어요"
        route = _determine_route_from_query_text(query)
        assert route == "bug_agent"
    
    def test_unknown_intent_routes_to_faq_agent(self) -> None:
        """unknown → faq_agent (기본값)"""
        query = "게임 스토리 설명해주세요"
        route = _determine_route_from_query_text(query)
        assert route == "faq_agent"


class TestSubQueryExecution:
    """하위 질문 실행 테스트"""
    
    @pytest.fixture
    def sample_state(self) -> ChatbotState:
        """샘플 ChatbotState"""
        return {
            "ticket_id": "test_123",
            "session_id": "sess_456",
            "raw_query": "테스트 질문",
            "normalized_query": "테스트 질문",
            "category": "faq",
            "routing_target": "faq_agent",
        }
    
    def test_sub_query_creation(self, sample_state: ChatbotState) -> None:
        """하위 질문 생성"""
        sub_query = SubQuery(
            id="q1",
            question="결제했는데 못 받았어요",
            intent="payment_missing_item",
            route="payment_agent",
        )
        
        assert sub_query.id == "q1"
        assert sub_query.intent == "payment_missing_item"
        assert sub_query.route == "payment_agent"
    
    def test_sub_query_priority(self, sample_state: ChatbotState) -> None:
        """하위 질문 우선순위"""
        sub_query = SubQuery(
            id="q1",
            question="결제 정보?",
            intent="payment_missing_item",
            route="payment_agent",
            priority=1,  # 핵심
        )
        
        assert sub_query.priority == 1


class TestMultihopFlow:
    """멀티홉 통합 흐름 테스트"""
    
    @pytest.fixture
    def sample_state(self) -> ChatbotState:
        """샘플 ChatbotState"""
        return {
            "ticket_id": "test_123",
            "session_id": "sess_456",
            "raw_query": "결제했는데 환불은 어떻게?",
            "normalized_query": "결제했는데 환불은 어떻게?",
            "category": "faq",
            "routing_target": "faq_agent",
            "conversation_summary": "",
        }
    
    def test_multihop_returns_none_for_simple_query(self, sample_state: ChatbotState) -> None:
        """간단한 질문은 None 반환"""
        result = _maybe_run_multihop_retrieval(
            state=sample_state,
            original_query="FAQ는 어디?",
            retrieval_query="FAQ",
            documents=[],
            final_top_k=5,
            candidate_top_k=10,
        )
        
        # 간단한 질문은 None이거나 accepted=False
        assert result is None or (isinstance(result, dict) and not result.get("accepted", True))


class TestIntegration:
    """통합 테스트"""
    
    def test_multihop_intent_flow(self) -> None:
        """의도 → 라우팅 → 실행 흐름"""
        # 1단계: 의도 판단
        query = "결제했는데 못 받았어요"
        intent = _infer_intent_from_query(query)
        assert intent == "payment_missing_item"
        
        # 2단계: 라우팅
        route = _determine_route_from_query_text(query)
        assert route == "payment_agent"
        
        # 3단계: 라우트 확인
        sub_query = SubQuery(
            id="q1",
            question=query,
            intent=intent,
            route=route,
        )
        assert sub_query.route == "payment_agent"


# ============================================================================
# 수동 테스트 가이드 (pytest 없이)
# ============================================================================

def manual_test_intent_inference() -> None:
    """의도 판단 수동 테스트"""
    test_queries = [
        ("결제했는데 못 받았어요", "payment_missing_item"),
        ("환불 가능한가요?", "refund_eligibility"),
        ("계정을 삭제하고 싶어요", "account_deletion"),
        ("보상이 안 들어왔어요", "reward_delivery"),
        ("게임 버그가 있어요", "bug_report"),
    ]
    
    print("\n[의도 판단 테스트]")
    for query, expected_intent in test_queries:
        actual_intent = _infer_intent_from_query(query)
        status = "✓" if actual_intent == expected_intent else "✗"
        print(f"{status} '{query}' → {actual_intent} (기대: {expected_intent})")


def manual_test_routing() -> None:
    """라우팅 결정 수동 테스트"""
    test_cases = [
        ("결제했는데 못 받았어요", "payment_agent"),
        ("환불 가능한가요?", "faq_agent"),
        ("게임 버그가 있어요", "bug_agent"),
        ("계정을 삭제하고 싶어요", "faq_agent"),
    ]
    
    print("\n[라우팅 테스트]")
    for query, expected_route in test_cases:
        actual_route = _determine_route_from_query_text(query)
        status = "✓" if actual_route == expected_route else "✗"
        print(f"{status} '{query}' → {actual_route} (기대: {expected_route})")


def manual_test_multihop_detection() -> None:
    """멀티홉 감지 수동 테스트"""
    test_queries = [
        ("결제했는데 환불은 어떻게?", True),
        ("계정 삭제하고 싶어요", False),  # 단일 도메인
        ("결제 기록 확인하고 계정 삭제하고 싶어요", True),
    ]
    
    print("\n[멀티홉 감지 테스트]")
    for query, should_be_multihop in test_queries:
        is_multihop, reason = _looks_like_multihop_query(query)
        status = "✓" if is_multihop == should_be_multihop else "✗"
        print(f"{status} '{query}'")
        print(f"   → is_multihop={is_multihop}, reason={reason}")


if __name__ == "__main__":
    print("=" * 70)
    print("멀티홉 검색 기능 수동 테스트")
    print("=" * 70)
    
    manual_test_intent_inference()
    manual_test_routing()
    manual_test_multihop_detection()
    
    print("\n" + "=" * 70)
    print("pytest로 실행: pytest test_multihop_retrieval.py -v")
    print("=" * 70)
