"""operation workflow 개별 노드·라우터 단위 테스트.

각 테스트는 DB·LLM 호출을 mock으로 차단하고 노드 함수 자체의
상태 변환 로직만 검증한다.
전체 경로 통합 테스트는 test_workflow_full.py 에서 별도 수행한다.
"""

from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


# 프로젝트 루트를 sys.path에 추가해 src.* 임포트가 동작하도록 한다.
# pytest가 루트에서 실행되지 않는 환경(IDE 직접 실행 등)에서도 동작한다.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.operation.workflow import nodes
from src.operation.workflow.prompts import (
    AnswerDraftResponse,
    HumanReviewResponse,
    QueryRoutingResponse,
    SafetyReviewResponse,
    TicketAnalysisResponse,
    UrgentDraftResponse,
)
from src.operation.workflow.state import AnalysisResult, EvidenceDocument, HumanReviewResult, OperationState


# ─── 공통 LLM fake ────────────────────────────────────────────────────────────

def fake_structured_llm(*, system_prompt, user_prompt, response_model):
    """모든 LLM 노드 테스트에서 공용으로 사용하는 고정 응답 반환기.

    실제 LLM API 호출 없이 각 response_model에 맞는 최소한의 유효 응답을 반환한다.
    nodes.invoke_structured_llm 을 patch할 때 이 함수를 대체자로 지정한다.

    응답 선택 기준:
    - QueryRoutingResponse  : payment (가장 일반적인 분류)
    - TicketAnalysisResponse: rag_reply / low (정상 경로 검증용)
    - AnswerDraftResponse   : evidence_doc_ids=["chunk-1"] (필터 검증을 위해 실제 ID 포함)
    - UrgentDraftResponse   : 단순 알림 텍스트
    - SafetyReviewResponse  : 모든 위험 항목 False, approved=True (승인 경로 검증용)
    - HumanReviewResponse   : edit 결정 (edited_answer 경로 검증용)
    """
    if response_model is QueryRoutingResponse:
        return QueryRoutingResponse(query_route="payment", route_reason="결제 문의")
    if response_model is TicketAnalysisResponse:
        return TicketAnalysisResponse(
            query_route="payment",
            target_route="rag_reply",
            risk_level="low",
            risk_reason="긴급 위험 없음",
            summary="결제 상태 확인 요청",
            required_actions=["결제 이력 확인"],
        )
    if response_model is AnswerDraftResponse:
        # evidence_doc_ids=["chunk-1"]: generate_answer_node의 유효 ID 필터 검증을 위해
        # state.evidence_doc_ids에 포함된 ID만 넘긴다
        return AnswerDraftResponse(answer_draft="결제 내역을 확인했습니다.", evidence_doc_ids=["chunk-1"])
    if response_model is UrgentDraftResponse:
        return UrgentDraftResponse(urgent_draft="운영자 확인이 필요합니다.")
    if response_model is SafetyReviewResponse:
        return SafetyReviewResponse(
            approved=True,
            evidence_matched=True,
            hallucination_detected=False,
            policy_violation_detected=False,
            unsafe_expression_detected=False,
            reasons=[],
        )
    if response_model is HumanReviewResponse:
        # decision="edit": edited_answer가 반드시 채워져야 하는 케이스
        return HumanReviewResponse(decision="edit", reason="문구 보완", edited_answer="수정된 답변입니다.")
    raise AssertionError(f"unexpected response model: {response_model}")


# ─── 1. load_ticket ───────────────────────────────────────────────────────────

class LoadTicketTest(unittest.TestCase):
    """load_ticket 노드 단위 테스트.

    load_ticket은 _fetch_ticket(ticket_id) 내부 헬퍼를 통해 DB에서 행을 읽는다.
    테스트에서는 _fetch_ticket 을 patch해 실제 DB 연결 없이 노드 로직만 검증한다.
    """

    # qa_ticket + community_users + game_accounts JOIN 결과의 최소 유효 행.
    # raw_query 필드가 Ticket.body 와 query_text 로 매핑되는 것을 확인하기 위해 포함한다.
    FAKE_ROW = {
        "ticket_id": 1001,
        "user_id": 1,
        "account_id": 101,        # Ticket.metadata["account_id"] 로 저장된다
        "title": "로그인 오류 문의",
        "raw_query": "로그인이 되지 않습니다.",  # → Ticket.body, query_text
        "source_type": "naver_cafe",             # → Ticket.channel
        "responder_type": "bot",
        "status": "pending",
        "inquiry_created_at": "2026-05-11 10:00:00",
    }

    def test_케이스1_유효한_ticket_id로_ticket_객체_필드_반환(self) -> None:
        """케이스1: DB에 있는 ticket_id → ticket 객체의 필드 정상 매핑 확인.

        검증 항목:
        - ticket.ticket_id: str로 변환되는지
        - ticket.user_id: str로 변환되는지
        - ticket.body: raw_query 값과 일치하는지
        - ticket.channel: source_type 값과 일치하는지
        - query_text: raw_query 와 동일하게 state에 저장되는지
        - ticket.metadata["account_id"]: int 원본값 유지 여부
        """
        with patch.object(nodes, "_fetch_ticket", return_value=self.FAKE_ROW):
            update = nodes.load_ticket(OperationState(ticket_id="1001"))

        self.assertEqual(update["ticket"].ticket_id, "1001")
        self.assertEqual(update["ticket"].user_id, "1")
        self.assertEqual(update["ticket"].body, "로그인이 되지 않습니다.")
        self.assertEqual(update["ticket"].channel, "naver_cafe")
        self.assertEqual(update["query_text"], "로그인이 되지 않습니다.")
        self.assertEqual(update["ticket"].metadata["account_id"], 101)

    def test_케이스2_없는_ticket_id_LookupError_발생(self) -> None:
        """케이스2: DB에 없는 ticket_id → LookupError 전파 확인.

        _fetch_ticket이 LookupError를 올리면 load_ticket이 이를 그대로 전파해야 한다.
        LangGraph는 노드에서 발생한 예외를 상위로 전달하므로 예외 미전파는 버그다.
        """
        with patch.object(nodes, "_fetch_ticket", side_effect=LookupError("qa_ticket not found: 9999")):
            with self.assertRaises(LookupError):
                nodes.load_ticket(OperationState(ticket_id="9999"))


# ─── 2. query_router / route_by_query ─────────────────────────────────────────

class QueryRouterTest(unittest.TestCase):
    """query_router 노드 및 route_by_query 라우터 단위 테스트.

    query_router는 invoke_structured_llm 을 호출해 문의 유형을 분류한다.
    ValidationError 발생 시 "policy" fallback으로 안전하게 처리하는지도 검증한다.
    """

    def test_케이스1_결제_문의_payment_route_반환(self) -> None:
        """케이스1: 결제 관련 문의 → query_route="payment" 정상 분류.

        invoke_structured_llm이 payment 응답을 반환하면
        노드가 이를 그대로 query_route에 저장하는지 확인한다.
        """
        state = OperationState(query_text="결제가 안됩니다")
        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            mock_llm.return_value = QueryRoutingResponse(
                query_route="payment", route_reason="결제 문의"
            )
            update = nodes.query_router(state)
        self.assertEqual(update["query_route"], "payment")

    def test_케이스2_장애_접속_문의_outage_route_반환(self) -> None:
        """케이스2: 장애/접속 실패 문의 → query_route="outage" 분류.

        payment 외의 route도 정상적으로 반환되는지 확인한다.
        """
        state = OperationState(query_text="서버 접속이 안됩니다")
        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            mock_llm.return_value = QueryRoutingResponse(
                query_route="outage", route_reason="서비스 접속 실패"
            )
            update = nodes.query_router(state)
        self.assertEqual(update["query_route"], "outage")

    def test_ValidationError_시_policy_fallback_반환(self) -> None:
        """LLM이 허용값 외 query_route를 반환해 ValidationError 발생 시 "policy" fallback 확인.

        실제 ValidationError 인스턴스를 미리 생성해 side_effect로 주입하는 이유:
        pydantic ValidationError는 생성자로 직접 만들 수 없으므로
        유효하지 않은 값으로 모델을 생성 시도해 예외를 채취한다.
        route_reason에 "fallback" 문자열이 포함되어야 LLM 오류임을 추적할 수 있다.
        """
        from pydantic import ValidationError
        try:
            QueryRoutingResponse(query_route="invalid_value", route_reason="test")
        except ValidationError as exc:
            ve = exc

        state = OperationState(query_text="문의입니다")
        with patch.object(nodes, "invoke_structured_llm", side_effect=ve):
            update = nodes.query_router(state)
        self.assertEqual(update["query_route"], "policy")
        self.assertIn("fallback", update["query_route_reason"])

    def test_route_by_query_케이스1_payment_route_키_반환(self) -> None:
        """route_by_query 케이스1: query_route="payment" → CONTEXT_NODE_BY_ROUTE 키 "payment" 반환.

        route_by_query는 LangGraph 조건부 엣지 함수로, 반환값이
        CONTEXT_NODE_BY_ROUTE의 키와 일치해야 올바른 노드로 분기된다.
        """
        self.assertEqual(nodes.route_by_query(OperationState(query_route="payment")), "payment")

    def test_route_by_query_케이스2_None이면_ValueError_발생(self) -> None:
        """route_by_query 케이스2: query_route=None → ValueError 발생.

        query_route 없이 라우터를 호출하면 즉시 예외를 올려야 한다.
        예외를 삼키면 잘못된 노드로 분기되는 침묵 버그가 발생한다.
        """
        with self.assertRaises(ValueError):
            nodes.route_by_query(OperationState())


# ─── 3. context 노드 ──────────────────────────────────────────────────────────

class ContextNodeTest(unittest.TestCase):
    """7종 context 노드 단위 테스트 (결과 있음 / 빈 결과).

    모든 context 노드는 내부적으로 _context_for_route(route, state) →
    _add_context(state, route) 순서로 실행된다.
    테스트에서는 _context_for_route 를 patch해 DB 없이 노드 로직만 검증한다.

    검증 핵심:
    1. context[route] 에 올바른 데이터 또는 빈 리스트가 저장되는지
    2. context_nodes 리스트에 해당 노드 이름이 추가되는지
       (context_nodes 는 운영 로그와 디버깅에 사용되므로 반드시 기록되어야 한다)
    """

    # ── 3-3. payment_context_node ──────────────────────────────────────────────

    def test_payment_context_node_context_dict에_payment_키_추가(self) -> None:
        """케이스1: 결제 내역 있는 ticket → context["payment"] rows 반환, context_nodes 기록."""
        state = OperationState(ticket_id="1001")
        # user_id, account_id는 payments JOIN 조건에서 사용된다
        state.ticket.user_id = "1"
        state.ticket.metadata = {"account_id": 101}

        with patch.object(nodes, "_context_for_route", return_value=[{"payment_id": 1, "amount": 9900}]):
            update = nodes.payment_context_node(state)

        self.assertEqual(update["context"]["payment"][0]["payment_id"], 1)
        self.assertEqual(update["context_nodes"], ["payment_context_node"])

    def test_케이스2_payment_context_node_결제_내역_없으면_빈_리스트(self) -> None:
        """케이스2: 결제 내역 없는 user → context["payment"] 빈 리스트.

        결제 내역이 없어도 context_nodes에는 노드 이름이 기록되어야 한다.
        빈 리스트도 유효한 context 값이므로 예외 없이 처리되어야 한다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[]):
            update = nodes.payment_context_node(state)

        self.assertEqual(update["context"]["payment"], [])
        self.assertEqual(update["context_nodes"], ["payment_context_node"])

    # ── 3-4. refund_context_node ───────────────────────────────────────────────

    def test_케이스1_refund_context_node_환불_내역_있는_user_rows_반환(self) -> None:
        """케이스1: 환불 내역 있는 user → context["refund"] rows 반환.

        refunds + payments + game_accounts JOIN 결과를 _context_for_route가 반환하는 구조.
        refund_id 와 status 필드가 dict 형태로 유지되는지 확인한다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[{"refund_id": 5, "status": "approved"}]):
            update = nodes.refund_context_node(state)

        self.assertEqual(update["context"]["refund"][0]["refund_id"], 5)
        self.assertEqual(update["context_nodes"], ["refund_context_node"])

    def test_케이스2_refund_context_node_환불_내역_없으면_빈_리스트(self) -> None:
        """케이스2: 환불 내역 없는 user → context["refund"] 빈 리스트."""
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[]):
            update = nodes.refund_context_node(state)

        self.assertEqual(update["context"]["refund"], [])
        self.assertEqual(update["context_nodes"], ["refund_context_node"])

    # ── 3-5. item_delivery_context_node ───────────────────────────────────────

    def test_케이스1_item_delivery_context_node_지급_내역_있는_계정_rows_반환(self) -> None:
        """케이스1: 지급 내역 있는 계정 → context["item_delivery"] rows 반환.

        item_delivery_logs + game_accounts JOIN 결과를 확인한다.
        item_name 필드로 어떤 아이템이 지급되었는지 운영자가 확인할 수 있다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[{"delivery_id": 3, "item_name": "월정액"}]):
            update = nodes.item_delivery_context_node(state)

        self.assertEqual(update["context"]["item_delivery"][0]["delivery_id"], 3)
        self.assertEqual(update["context_nodes"], ["item_delivery_context_node"])

    def test_케이스2_item_delivery_context_node_지급_내역_없으면_빈_리스트(self) -> None:
        """케이스2: 지급 내역 없는 계정 → context["item_delivery"] 빈 리스트."""
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[]):
            update = nodes.item_delivery_context_node(state)

        self.assertEqual(update["context"]["item_delivery"], [])
        self.assertEqual(update["context_nodes"], ["item_delivery_context_node"])

    # ── 3-6. gacha_context_node ───────────────────────────────────────────────

    def test_케이스1_gacha_context_node_가챠_이력_있는_계정_rows_반환(self) -> None:
        """케이스1: 가챠 이력 있는 계정 → context["gacha"] rows 반환.

        gacha_logs + game_accounts JOIN 결과를 확인한다.
        banner 필드로 어떤 배너에서 뽑았는지 운영자가 확인할 수 있다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[{"gacha_id": 7, "banner": "한정 배너"}]):
            update = nodes.gacha_context_node(state)

        self.assertEqual(update["context"]["gacha"][0]["gacha_id"], 7)
        self.assertEqual(update["context_nodes"], ["gacha_context_node"])

    def test_케이스2_gacha_context_node_가챠_이력_없으면_빈_리스트(self) -> None:
        """케이스2: 가챠 이력 없는 계정 → context["gacha"] 빈 리스트."""
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[]):
            update = nodes.gacha_context_node(state)

        self.assertEqual(update["context"]["gacha"], [])
        self.assertEqual(update["context_nodes"], ["gacha_context_node"])

    # ── 3-7. policy_context_node ──────────────────────────────────────────────

    def test_케이스1_policy_context_node_정책_문서_존재_rows_반환(self) -> None:
        """케이스1: policy 문서 존재 → context["policy"] rows 반환.

        documents WHERE category ILIKE '%policy%' 결과를 확인한다.
        documents_id 와 title 필드가 dict로 유지되는지 확인한다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[{"documents_id": 1, "title": "이용약관"}]):
            update = nodes.policy_context_node(state)

        self.assertEqual(update["context"]["policy"][0]["documents_id"], 1)
        self.assertEqual(update["context_nodes"], ["policy_context_node"])

    def test_케이스2_policy_context_node_정책_문서_없으면_빈_리스트(self) -> None:
        """케이스2: 정책 문서 없으면 → context["policy"] 빈 리스트.

        RAG에서 policy context가 비어 있으면 LLM은 일반 가이드 기반으로만 답변한다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[]):
            update = nodes.policy_context_node(state)

        self.assertEqual(update["context"]["policy"], [])
        self.assertEqual(update["context_nodes"], ["policy_context_node"])

    # ── 3-8. abuse_context_node ───────────────────────────────────────────────

    def test_케이스1_abuse_context_node_인사이트_있는_user_rows_반환(self) -> None:
        """케이스1: 어뷰징 인사이트 있는 user → context["abuse"] rows 반환.

        insight + voc_feedback LEFT JOIN 결과를 확인한다.
        label 필드로 어떤 유형의 어뷰징인지 운영자가 판단할 수 있다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[{"insight_id": 2, "label": "abuse"}]):
            update = nodes.abuse_context_node(state)

        self.assertEqual(update["context"]["abuse"][0]["insight_id"], 2)
        self.assertEqual(update["context_nodes"], ["abuse_context_node"])

    def test_케이스2_abuse_context_node_인사이트_없는_user_빈_리스트(self) -> None:
        """케이스2: 어뷰징 인사이트 없는 user → context["abuse"] 빈 리스트.

        인사이트가 없는 사용자도 abuse route로 분류될 수 있으므로
        빈 결과 처리가 정상 동작해야 한다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[]):
            update = nodes.abuse_context_node(state)

        self.assertEqual(update["context"]["abuse"], [])
        self.assertEqual(update["context_nodes"], ["abuse_context_node"])

    # ── 3-9. outage_context_node ──────────────────────────────────────────────

    def test_케이스1_outage_context_node_장애_문서_존재_rows_반환(self) -> None:
        """케이스1: 장애 공지 문서 존재 → context["outage"] rows 반환.

        documents WHERE category ILIKE '%outage%' 결과를 확인한다.
        서버 점검 공지가 있으면 analyze_ticket이 긴급 대응 여부를 판단할 수 있다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[{"documents_id": 9, "title": "서버 점검 안내"}]):
            update = nodes.outage_context_node(state)

        self.assertEqual(update["context"]["outage"][0]["documents_id"], 9)
        self.assertEqual(update["context_nodes"], ["outage_context_node"])

    def test_케이스2_outage_context_node_장애_문서_없으면_빈_리스트(self) -> None:
        """케이스2: 장애 공지 문서 없으면 → context["outage"] 빈 리스트.

        장애 공지가 없어도 outage route로 분류될 수 있으므로
        빈 결과 처리가 정상 동작해야 한다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "_context_for_route", return_value=[]):
            update = nodes.outage_context_node(state)

        self.assertEqual(update["context"]["outage"], [])
        self.assertEqual(update["context_nodes"], ["outage_context_node"])


# ─── 4. analyze_ticket / route_by_target ──────────────────────────────────────

class AnalyzeTicketTest(unittest.TestCase):
    """analyze_ticket 노드 및 route_by_target 라우터 단위 테스트.

    analyze_ticket은 LLM이 반환한 risk_level 과 target_route를 state에 저장한다.
    critical 위험도 또는 target_route="urgent_alert" 이면 긴급 알림 경로로 분기된다.
    """

    def test_케이스1_일반_문의_rag_reply_low_risk(self) -> None:
        """케이스1: 일반 문의 → target_route="rag_reply", risk_level="low".

        RAG 답변 경로로 분기되는 정상 케이스를 검증한다.
        analysis 객체의 risk_level 이 "low" 로 저장되어야 한다.
        """
        state = OperationState(query_text="결제 확인", query_route="payment")
        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            mock_llm.return_value = TicketAnalysisResponse(
                query_route="payment",
                target_route="rag_reply",
                risk_level="low",
                risk_reason="일반 문의",
                summary="결제 확인 요청",
            )
            update = nodes.analyze_ticket(state)
        self.assertEqual(update["target_route"], "rag_reply")
        self.assertEqual(update["analysis"].risk_level, "low")

    def test_케이스2_위험_문의_urgent_alert_critical_risk(self) -> None:
        """케이스2: 위험 문의 → target_route="urgent_alert", risk_level in {"high", "critical"}.

        계정 탈취 의심 등 고위험 케이스에서 긴급 알림 경로로 분기되는지 확인한다.
        risk_level이 high 또는 critical 이면 조건을 충족한다.
        """
        state = OperationState(query_text="계정 해킹 의심", query_route="abuse")
        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            mock_llm.return_value = TicketAnalysisResponse(
                query_route="abuse",
                target_route="urgent_alert",
                risk_level="critical",
                risk_reason="계정 탈취 의심",
                summary="긴급 계정 보안 이슈",
            )
            update = nodes.analyze_ticket(state)
        self.assertEqual(update["target_route"], "urgent_alert")
        self.assertIn(update["analysis"].risk_level, {"high", "critical"})

    def test_route_by_target_케이스1_rag_reply_반환(self) -> None:
        """route_by_target 케이스1: target_route="rag_reply" → "rag_reply" 반환.

        TARGET_ROUTE_TARGETS = {"rag_reply": "rag_retrieve_node", ...} 와 연결되는
        조건부 엣지 라우터의 반환값을 검증한다.
        """
        self.assertEqual(nodes.route_by_target(OperationState(target_route="rag_reply")), "rag_reply")

    def test_route_by_target_케이스2_None이면_ValueError_발생(self) -> None:
        """route_by_target 케이스2: target_route=None → ValueError 발생.

        분석 결과 없이 라우터가 호출되면 즉시 예외를 올려야 한다.
        """
        with self.assertRaises(ValueError):
            nodes.route_by_target(OperationState())


# ─── 5. save_draft_node ───────────────────────────────────────────────────────

class SaveDraftNodeTest(unittest.TestCase):
    """save_draft_node 단위 테스트.

    save_draft_node는 answer_draft 를 answer_draft 테이블에 INSERT하고
    RETURNING draft_id 로 PK를 받아 state에 저장한다.
    케이스1(정상 INSERT)은 실DB 필요 → 전체 경로 테스트(test_workflow_full.py)에서 간접 확인.
    케이스2(사전 차단)는 DB 없이 검증 가능하므로 여기서 단독 테스트한다.
    """

    def test_케이스2_analysis_id_없으면_errors_기록_예외_미전파(self) -> None:
        """케이스2: analysis_id=None → state.errors 기록, 예외 미전파 (DB 호출 없음).

        analysis_id는 answer_draft 테이블의 FK이므로 누락 시 DB INSERT가 실패한다.
        save_draft_node는 DB 호출 전에 analysis_id를 사전 체크해 errors에 기록하고
        예외 없이 반환해야 한다 (LangGraph 워크플로우가 중단되지 않아야 함).
        """
        state = OperationState(ticket_id="1001", answer_draft="초안 텍스트")
        # analysis_id를 None으로 두면 사전 차단 분기에서 반환
        update = nodes.save_draft_node(state)
        self.assertIsInstance(update, dict)
        self.assertTrue(len(update.get("errors", [])) > 0)
        self.assertIn("analysis_id", update["errors"][0])


# ─── 6. route_after_save_draft ────────────────────────────────────────────────

class RouteAfterSaveDraftTest(unittest.TestCase):
    """route_after_save_draft 라우터 단위 테스트.

    분기 기준:
    1. target_route="urgent_alert" → "urgent_alert" (근거 수 무관)
    2. len(retrieved_docs) >= _MIN_EVIDENCE_COUNT(=2) → "save_evidence_docs"
    3. len(retrieved_docs) < 2 → "human_review" (근거 부족 → 사람 검수)
    """

    def test_케이스1_근거_2건_이상_save_evidence_docs_반환(self) -> None:
        """케이스1: retrieved_docs 3건 → "save_evidence_docs" 반환.

        _MIN_EVIDENCE_COUNT=2 기준을 충족하므로 근거 저장 후 승인 게이트로 진행한다.
        """
        state = OperationState(retrieved_docs=[
            EvidenceDocument(doc_id="chunk-1"),
            EvidenceDocument(doc_id="chunk-2"),
            EvidenceDocument(doc_id="chunk-3"),
        ])
        self.assertEqual(nodes.route_after_save_draft(state), "save_evidence_docs")

    def test_케이스2_근거_1건_human_review_반환(self) -> None:
        """케이스2: retrieved_docs 1건 (< _MIN_EVIDENCE_COUNT=2) → "human_review" 반환.

        근거가 부족하면 자동 승인 대신 사람이 직접 검수해야 한다.
        """
        state = OperationState(retrieved_docs=[EvidenceDocument(doc_id="chunk-1")])
        self.assertEqual(nodes.route_after_save_draft(state), "human_review")

    def test_케이스3_urgent_alert_target_route_urgent_alert_반환(self) -> None:
        """케이스3: target_route="urgent_alert" → "urgent_alert" 반환 (근거 수 무관).

        긴급 알림 경로는 RAG 근거 수와 무관하게 즉시 분기된다.
        urgent_draft_node → save_draft_node 경유 후 이 라우터에 도달하는 흐름이다.
        """
        state = OperationState(target_route="urgent_alert")
        self.assertEqual(nodes.route_after_save_draft(state), "urgent_alert")

    def test_근거_없으면_human_review_반환(self) -> None:
        """retrieved_docs 0건 → "human_review" 반환.

        빈 상태도 < _MIN_EVIDENCE_COUNT 조건에 해당하므로 human_review로 분기된다.
        """
        self.assertEqual(nodes.route_after_save_draft(OperationState()), "human_review")


# ─── 7. 라우터 필수값 검증 ────────────────────────────────────────────────────

class RouterValidationTest(unittest.TestCase):
    """모든 라우터 함수의 필수값 검증 단위 테스트.

    route_by_query / route_by_target / route_by_approval / route_by_human_decision
    4개 라우터 모두 필수 state 값이 None이면 ValueError를 올려야 한다.
    LangGraph는 라우터가 None을 반환하면 잘못된 노드로 분기할 수 있으므로
    예외로 명시적으로 실패시키는 것이 안전하다.
    """

    def test_필수값_없으면_ValueError_발생(self) -> None:
        """4개 라우터 모두 필수 값 누락 시 ValueError 발생 확인."""
        with self.assertRaises(ValueError):
            nodes.route_by_query(OperationState())
        with self.assertRaises(ValueError):
            nodes.route_by_target(OperationState())
        with self.assertRaises(ValueError):
            nodes.route_by_approval(OperationState())
        with self.assertRaises(ValueError):
            nodes.route_by_human_decision(OperationState())

    def test_유효한_값이면_정상_반환(self) -> None:
        """4개 라우터 모두 유효한 값이 있을 때 해당 값을 그대로 반환하는지 확인.

        각 라우터는 state에서 값을 꺼내 LangGraph 엣지 타겟 딕셔너리의 키로 반환한다.
        반환값이 해당 딕셔너리에 없는 값이면 LangGraph 런타임 오류가 발생하므로
        허용값 그대로 반환되는지 확인한다.
        """
        state = OperationState(
            query_route="payment",
            target_route="rag_reply",
            approval_route="approved",
            human_decision="approved",
        )
        self.assertEqual(nodes.route_by_query(state), "payment")
        self.assertEqual(nodes.route_by_target(state), "rag_reply")
        self.assertEqual(nodes.route_by_approval(state), "approved")
        self.assertEqual(nodes.route_by_human_decision(state), "approved")


# ─── 8. LLM 노드 상태 업데이트 통합 ──────────────────────────────────────────

class LlmNodesStateUpdateTest(unittest.TestCase):
    """LLM 노드들이 올바른 상태값을 반환하는지 통합 검증.

    6개 LLM 노드(query_router, analyze_ticket, generate_answer_node,
    urgent_draft_node, approval_gate_node, human_review_node)를 한 번에 호출해
    각각의 핵심 state 업데이트 키를 확인한다.

    개별 노드 테스트에서 잡지 못하는 노드 간 상태 전달 누락을 빠르게 감지하기 위한 테스트다.
    """

    def test_llm_노드들_올바른_상태값_반환(self) -> None:
        """6개 LLM 노드가 각각 올바른 핵심 state 키를 업데이트하는지 확인.

        state 초기화 주의사항:
        - retrieved_docs=["chunk-1"]: generate_answer_node가 LLM 응답의
          evidence_doc_ids를 이 목록과 교차 검증해 유효 ID만 남기므로 필수
        - evidence_doc_ids=["chunk-1"]: rag_retrieve_node가 설정하는 값으로,
          generate_answer_node의 필터 기준이 된다. 없으면 필터 결과가 빈 리스트가 된다
        """
        state = OperationState(
            ticket_id="1001",
            query_text="결제 내역 확인",
            retrieved_docs=[EvidenceDocument(doc_id="chunk-1", content="결제 정책")],
            # rag_retrieve_node가 설정하는 값 — generate_answer_node의 evidence_doc_ids 필터 기준
            evidence_doc_ids=["chunk-1"],
        )

        with patch.object(nodes, "invoke_structured_llm", fake_structured_llm):
            route_update = nodes.query_router(state)
            analysis_update = nodes.analyze_ticket(state)
            answer_update = nodes.generate_answer_node(state)
            urgent_update = nodes.urgent_draft_node(state)
            safety_update = nodes.approval_gate_node(state)
            review_update = nodes.human_review_node(state)

        # query_router: query_route 설정
        self.assertEqual(route_update["query_route"], "payment")
        # analyze_ticket: target_route 설정
        self.assertEqual(analysis_update["target_route"], "rag_reply")
        # generate_answer_node: 유효 ID 필터 후 evidence_doc_ids 설정
        self.assertEqual(answer_update["evidence_doc_ids"], ["chunk-1"])
        # urgent_draft_node: urgent_draft 와 answer_draft 모두 설정
        self.assertEqual(urgent_update["answer_draft"], "운영자 확인이 필요합니다.")
        # approval_gate_node: SafetyReviewResponse.approved=True → approval_route="approved"
        self.assertEqual(safety_update["approval_route"], "approved")
        # human_review_node: HumanReviewResponse.decision="edit" → human_decision="edit"
        self.assertEqual(review_update["human_decision"], "edit")


# ─── 9. retry_routing_node / route_after_retry ────────────────────────────────

class RetryRoutingNodeTest(unittest.TestCase):
    """retry_routing_node 및 route_after_retry 라우터 단위 테스트.

    retry_routing_node는 반려 후 재시도 흐름을 관리한다:
    - retry_count +1
    - answer_draft / urgent_draft / approval_route / human_decision 초기화 (재생성 준비)
    - human_review.reason → metadata["retry_reason"] 저장 (다음 LLM 프롬프트에 주입됨)
    - retry_count >= max_retries 이면 approval_route="urgent_alert" 설정
    """

    def test_케이스1_retry_count_증가_retry_reason_저장(self) -> None:
        """케이스1: retry_count=0 → retry_count=1, metadata["retry_reason"] 채워짐.

        재시도 후 이전 초안 관련 state를 초기화해야
        query_router 재진입 시 오래된 답변이 남아 있지 않다.
        """
        state = OperationState(
            retry_count=0,
            # human_review.reason이 metadata["retry_reason"]으로 저장된다
            human_review=HumanReviewResult(reason="초안 오류 있음"),
        )
        update = nodes.retry_routing_node(state)
        self.assertEqual(update["retry_count"], 1)
        self.assertEqual(update["metadata"]["retry_reason"], "초안 오류 있음")
        # 재시도 전 초안·승인·검수 결과는 모두 초기화되어야 한다
        self.assertIsNone(update["answer_draft"])
        self.assertIsNone(update["urgent_draft"])
        self.assertIsNone(update["approval_route"])

    def test_케이스2_max_retries_도달_시_urgent_alert_설정(self) -> None:
        """케이스2: retry_count=3, max_retries=3 → approval_route="urgent_alert" 설정.

        max_retries에 도달하면 더 이상 query_router로 돌아가지 않고
        urgent_alert_node로 에스컬레이션한다.
        route_after_retry가 이 approval_route 값을 읽어 분기를 결정한다.
        """
        state = OperationState(
            retry_count=3,
            max_retries=3,
            human_review=HumanReviewResult(reason="반복 반려"),
        )
        update = nodes.retry_routing_node(state)
        # retry_count는 4가 되지만 max_retries 초과이므로 urgent_alert로 에스컬레이션
        self.assertEqual(update["retry_count"], 4)
        self.assertEqual(update["approval_route"], "urgent_alert")

    def test_route_after_retry_케이스1_횟수_미초과_query_router_반환(self) -> None:
        """route_after_retry 케이스1: count=1, max=3 → "query_router" 반환.

        재시도 횟수가 남아 있으면 query_router로 돌아가 재분류부터 다시 시작한다.
        """
        state = OperationState(retry_count=1, max_retries=3)
        self.assertEqual(nodes.route_after_retry(state), "query_router")

    def test_route_after_retry_케이스2_횟수_초과_urgent_alert_node_반환(self) -> None:
        """route_after_retry 케이스2: count=3, max=3 → "urgent_alert_node" 반환.

        retry_count >= max_retries 조건으로 직접 판단한다.
        approval_route 플래그에만 의존하지 않아 max_retries 변경 시에도 일관성을 유지한다.
        """
        state = OperationState(retry_count=3, max_retries=3)
        self.assertEqual(nodes.route_after_retry(state), "urgent_alert_node")


# ─── 10. edit_answer_node / save_final_edit_node ──────────────────────────────

class EditPathNodeTest(unittest.TestCase):
    """edit 경로 노드 단위 테스트.

    human_review_node가 decision="edit"을 반환한 뒤의 흐름:
    edit_answer_node → save_final_edit_node → publish_final_answer_node
    (workflow.md §2, langgraph.mmd 에 명시된 경로)

    save_final_edit_node는 DB write 없이 state만 업데이트한다.
    향후 수정 이력 별도 저장이 필요하면 이 노드에 INSERT를 추가한다 (todolist.md P3).
    """

    def test_edit_answer_node_human_review_edited_answer_반영(self) -> None:
        """edit_answer_node: human_review.edited_answer → state.edited_answer 설정.

        운영자가 수정한 답변을 state.edited_answer에 옮겨
        save_final_edit_node가 final_answer로 확정할 수 있게 한다.
        """
        state = OperationState(
            human_review=HumanReviewResult(
                decision="edit", reason="문구 수정", edited_answer="수정된 답변"
            )
        )
        update = nodes.edit_answer_node(state)
        self.assertEqual(update["edited_answer"], "수정된 답변")

    def test_케이스1_save_final_edit_node_edited_answer_있으면_final_answer_설정(self) -> None:
        """케이스1: edited_answer 있을 때 → final_answer 에 복사.

        save_final_edit_node는 edited_answer를 final_answer로 확정한다.
        publish_final_answer_node는 final_answer 값을 사용해 final_response에 저장한다.
        """
        state = OperationState(edited_answer="최종 수정 답변")
        update = nodes.save_final_edit_node(state)
        self.assertEqual(update["final_answer"], "최종 수정 답변")

    def test_save_final_edit_node_edited_answer_없으면_errors_기록(self) -> None:
        """edited_answer=None → state.errors 기록, 예외 미전파.

        edit 경로에서 edited_answer 없이 save_final_edit_node가 호출되면
        워크플로우를 중단하지 않고 errors에 기록해 운영자가 추적할 수 있게 한다.
        """
        update = nodes.save_final_edit_node(OperationState())
        self.assertTrue(len(update.get("errors", [])) > 0)


# ─── rag_retrieve_node 용 가짜 DB ────────────────────────────────────────────
# rag_retrieve_node는 conn.cursor(row_factory=dict_row) 로 커서를 만들고
# BM25 / pgvector 두 번 execute → fetchall() 을 호출한다.
# row_factory 파라미터는 가짜 커서에서 무시하고, fetchall은 항상 같은 rows를 반환한다.

class _FakeRagCursor:
    """rag_retrieve_node BM25 검색 결과를 흉내 내는 가짜 커서."""

    def __init__(self, rows: list) -> None:
        self._rows = rows

    def __enter__(self) -> "_FakeRagCursor":
        return self

    def __exit__(self, *_) -> None:
        pass

    def execute(self, *_) -> None:
        # SQL 내용과 무관하게 동일한 rows를 반환한다 (BM25/vector 구분 없음)
        pass

    def fetchall(self) -> list:
        return list(self._rows)


class _FakeRagConn:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def cursor(self, **_) -> _FakeRagCursor:
        # row_factory=dict_row 파라미터는 무시한다
        return _FakeRagCursor(self._rows)


def _fake_rag_db(rows: list):
    """지정한 rows를 fetchall로 반환하는 가짜 db_connection을 만든다."""
    @contextmanager
    def _conn():
        yield _FakeRagConn(rows)
    return _conn


class _RaisingCtx:
    """__enter__ 에서 Exception을 발생시키는 컨텍스트 매니저."""

    def __enter__(self):
        raise Exception("DB connection failed (fake)")

    def __exit__(self, *_) -> None:
        pass


def _raising_db():
    """모든 DB 연결 시도에서 Exception을 발생시키는 가짜 db_connection.

    @contextmanager 대신 클래스 기반으로 구현해 unreachable yield 경고를 방지한다.
    """
    return _RaisingCtx()


# ─── 11. save_analysis ────────────────────────────────────────────────────────

class SaveAnalysisTest(unittest.TestCase):
    """save_analysis 노드 단위 테스트.

    케이스1(정상 INSERT → analysis_id 반환)은 실 DB 필요 → test_workflow_full.py 에서 간접 확인.
    케이스2(DB 오류 → errors 기록)는 가짜 db_connection으로 DB 없이 검증한다.
    """

    def _make_state(self) -> OperationState:
        """save_analysis에 필요한 최소 유효 state를 생성한다.

        save_analysis는 try 블록 진입 전에 _ticket_key / _query_text 를 호출하므로
        ticket_id 와 analysis 필드가 반드시 설정되어야 한다.
        """
        state = OperationState(
            ticket_id="1001",
            query_text="결제 확인",
        )
        # INSERT에 필요한 analysis 필드 설정
        state.analysis.query_route = "payment"
        state.analysis.target_route = "rag_reply"
        state.analysis.risk_level = "low"
        state.analysis.risk_reason = "일반 문의"
        state.analysis.summary = "결제 확인 요청"
        return state

    def test_케이스2_DB_오류_시_errors_기록_예외_미전파(self) -> None:
        """케이스2: DB 연결 실패 → state.errors에 오류 메시지 추가, 예외 미전파.

        save_analysis는 try/except Exception으로 감싸져 있어
        DB 오류가 발생해도 워크플로우가 중단되지 않고 errors에 기록한다.
        errors[0]에 ticket_id가 포함되어 어떤 티켓에서 오류가 발생했는지 추적할 수 있다.
        """
        state = self._make_state()

        with patch.object(nodes, "db_connection", _raising_db):
            update = nodes.save_analysis(state)

        self.assertIsInstance(update, dict)
        self.assertTrue(len(update.get("errors", [])) > 0)
        # 오류 메시지에 ticket_id가 포함되어야 추적이 가능하다
        self.assertIn("1001", update["errors"][0])


# ─── 12. rag_retrieve_node ────────────────────────────────────────────────────

class RagRetrieveNodeTest(unittest.TestCase):
    """rag_retrieve_node 단위 테스트.

    BM25 + pgvector hybrid retrieval 노드.
    get_query_embedding=None 으로 패치해 임베딩 API 호출 없이
    BM25 단독 경로만 검증한다 (vector 경로는 get_query_embedding != None일 때만 실행).
    """

    # BM25 검색 결과를 흉내 내는 최소 유효 chunk row.
    # chunk_id, source_type, title, chunk_text, score, document_id 는
    # EvidenceDocument 생성과 _rrf_merge 에서 모두 사용된다.
    FAKE_BM25_ROWS = [
        {
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "source_type": "policy",
            "category": "payment",
            "title": "결제 안내",
            "chunk_text": "결제 완료 후 아이템 지급 상태를 확인합니다.",
            "score": 0.8,
        }
    ]

    def test_케이스1_BM25_검색_결과_있으면_retrieved_docs_채워짐(self) -> None:
        """케이스1: 유효한 query_text → retrieved_docs 1건 이상, evidence_doc_ids 채워짐.

        BM25 fake cursor가 1건의 chunk row를 반환할 때
        retrieved_docs에 EvidenceDocument가 생성되고
        evidence_doc_ids에 chunk_id가 저장되는지 확인한다.
        """
        state = OperationState(ticket_id="1001", query_text="결제 확인")

        with patch.object(nodes, "db_connection", _fake_rag_db(self.FAKE_BM25_ROWS)):
            # get_query_embedding=None → pgvector 검색 건너뜀, BM25 단독 실행
            with patch.object(nodes, "get_query_embedding", return_value=None):
                update = nodes.rag_retrieve_node(state)

        self.assertGreater(len(update["retrieved_docs"]), 0)
        self.assertIn("chunk-1", update["evidence_doc_ids"])

    def test_케이스2_get_query_embedding_None이면_BM25_단독_결과_반환(self) -> None:
        """케이스2: get_query_embedding=None(임베딩 실패) → BM25 결과만으로 retrieved_docs 반환.

        임베딩 API 장애 시 BM25 fallback이 동작하는지 확인한다.
        vector 검색 없이도 retrieved_docs가 채워져야 한다.
        """
        state = OperationState(ticket_id="1001", query_text="결제 확인")

        with patch.object(nodes, "db_connection", _fake_rag_db(self.FAKE_BM25_ROWS)):
            with patch.object(nodes, "get_query_embedding", return_value=None):
                update = nodes.rag_retrieve_node(state)

        # 임베딩 없이도 BM25 결과가 retrieved_docs에 담겨야 한다
        self.assertGreater(len(update["retrieved_docs"]), 0)
        self.assertEqual(update["retrieved_docs"][0].doc_id, "chunk-1")


# ─── 13. generate_answer_node 케이스2 ─────────────────────────────────────────

class GenerateAnswerNodeTest(unittest.TestCase):
    """generate_answer_node 누락 케이스 단위 테스트.

    케이스1(정상 답변)은 LlmNodesStateUpdateTest에서 간접 확인.
    케이스2(LLM 빈 초안)를 별도로 검증한다.
    """

    def test_케이스2_LLM_빈_초안_반환_시_answer_draft_None_errors_기록(self) -> None:
        """케이스2: LLM이 빈 문자열 answer_draft 반환 → answer_draft=None, errors에 기록.

        빈 초안을 그대로 고객에게 전송하는 것을 방지하기 위해
        strip() 후 빈값이면 None으로 강제하고 errors에 기록한다.
        answer_draft=None인 채로 이후 노드에 전달되므로 워크플로우가 중단되지 않는다.
        """
        state = OperationState(
            ticket_id="1001",
            query_text="결제 확인",
            retrieved_docs=[EvidenceDocument(doc_id="chunk-1", content="결제 정책")],
            # evidence_doc_ids는 rag_retrieve_node가 설정하는 값 — 필터 기준
            evidence_doc_ids=["chunk-1"],
        )

        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            # 빈 문자열 반환 → strip() 후 빈값 → answer_draft=None 처리
            mock_llm.return_value = AnswerDraftResponse(answer_draft="", evidence_doc_ids=[])
            update = nodes.generate_answer_node(state)

        self.assertIsNone(update["answer_draft"])
        self.assertTrue(len(update.get("errors", [])) > 0)
        self.assertIn("empty", update["errors"][0])


# ─── 14. urgent_draft_node 케이스2 ────────────────────────────────────────────

class UrgentDraftNodeTest(unittest.TestCase):
    """urgent_draft_node 누락 케이스 단위 테스트.

    케이스1(정상 생성)은 LlmNodesStateUpdateTest에서 간접 확인.
    케이스2(LLM 빈값)를 별도로 검증한다.
    """

    def test_케이스2_LLM_빈_urgent_draft_반환_시_None_errors_기록(self) -> None:
        """케이스2: LLM이 빈 문자열 urgent_draft 반환 → urgent_draft=None, errors에 기록.

        긴급 알림 메시지가 비어 있으면 운영자에게 의미 없는 알림이 전송되므로
        빈값을 None으로 강제하고 errors에 기록한다.
        urgent_alert_node가 urgent_draft=None인 채로 호출되므로 이후 처리에 주의가 필요하다.
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            # 빈 문자열 반환 → strip() 후 빈값 → urgent_draft=None 처리
            mock_llm.return_value = UrgentDraftResponse(urgent_draft="")
            update = nodes.urgent_draft_node(state)

        self.assertIsNone(update["urgent_draft"])
        self.assertTrue(len(update.get("errors", [])) > 0)
        self.assertIn("empty", update["errors"][0])


# ─── 16. save_evidence_docs_node 케이스2 ──────────────────────────────────────

class SaveEvidenceDocsNodeTest(unittest.TestCase):
    """save_evidence_docs_node 누락 케이스 단위 테스트.

    케이스1(cited_docs 있을 때 INSERT)은 test_workflow_full.py에서 간접 확인.
    케이스2(cited_docs 빈 리스트)는 DB 없이 검증 가능하므로 여기서 단독 테스트한다.
    """

    def test_케이스2_cited_docs_빈_리스트_INSERT_없음_evidence_empty(self) -> None:
        """케이스2: evidence_doc_ids 빈 리스트 → cited_docs=[], INSERT 없음, status="evidence_empty".

        generate_answer_node 필터 후 인용 ID가 없으면 DB 호출 없이
        status="evidence_empty"와 errors를 반환한다.
        draft_id는 설정되어 있어야 첫 번째 사전 차단을 통과한다.
        """
        state = OperationState(
            ticket_id="1001",
            draft_id=1,              # draft_id 사전 차단 통과용
            retrieved_docs=[],       # 검색 결과 없음
            evidence_doc_ids=[],     # LLM 인용 ID 없음 → cited_docs=[]
        )

        # DB 호출이 없어야 하므로 db_connection은 패치하지 않는다
        update = nodes.save_evidence_docs_node(state)

        self.assertEqual(update.get("status"), "evidence_empty")
        self.assertTrue(len(update.get("errors", [])) > 0)


# ─── 17. approval_gate_node 케이스2 ───────────────────────────────────────────

class ApprovalGateNodeTest(unittest.TestCase):
    """approval_gate_node 누락 케이스 단위 테스트.

    케이스1(approved)은 LlmNodesStateUpdateTest에서 간접 확인.
    케이스2(policy_violation → urgent_alert 강제)를 별도로 검증한다.
    """

    def test_케이스2_policy_violation_True이면_approved여도_urgent_alert_강제(self) -> None:
        """케이스2: policy_violation_detected=True → approval_route="urgent_alert" 강제.

        approved=True라도 정책 위반이 감지되면 urgent_alert를 우선한다.
        운영자가 반드시 직접 확인해야 하는 케이스이기 때문이다.
        (nodes.py: if response.policy_violation_detected or risk_level=="critical" → urgent_alert)
        """
        state = OperationState(ticket_id="1001")

        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            # approved=True이지만 policy_violation_detected=True → urgent_alert 강제
            mock_llm.return_value = SafetyReviewResponse(
                approved=True,
                evidence_matched=True,
                hallucination_detected=False,
                policy_violation_detected=True,   # 정책 위반 감지
                unsafe_expression_detected=False,
                reasons=["정책 위반 표현 포함"],
            )
            update = nodes.approval_gate_node(state)

        # approved여도 policy_violation이면 urgent_alert가 우선이다
        self.assertEqual(update["approval_route"], "urgent_alert")


# ─── 18. save_safety_result_node 케이스2 ──────────────────────────────────────

class SaveSafetyResultNodeTest(unittest.TestCase):
    """save_safety_result_node 누락 케이스 단위 테스트.

    케이스1(정상 INSERT → safety_id 반환)은 test_workflow_full.py에서 간접 확인.
    케이스2(draft_id=None → ValueError)는 DB 없이 검증 가능하다.
    """

    def test_케이스2_draft_id_None이면_ValueError_발생(self) -> None:
        """케이스2: draft_id=None → ValueError 발생 (DB 호출 전 사전 차단).

        safety_results는 answer_draft.draft_id를 FK로 가지므로
        draft_id 없이 INSERT를 시도하면 DB FK 위반이 발생한다.
        노드는 DB 호출 전에 ValueError를 올려 즉시 실패를 명시한다.
        (save_draft_node와 달리 예외를 삼키지 않고 전파한다)
        """
        state = OperationState()  # draft_id=None 기본값

        with self.assertRaises(ValueError):
            nodes.save_safety_result_node(state)


# ─── 19. publish_final_answer_node 케이스2 ────────────────────────────────────

class PublishFinalAnswerNodeTest(unittest.TestCase):
    """publish_final_answer_node 누락 케이스 단위 테스트.

    케이스1(정상 INSERT → response_id, status="closed")은 test_workflow_full.py에서 간접 확인.
    케이스2(최종 답변 텍스트 없음 → ValueError)는 DB 없이 검증 가능하다.
    """

    def test_케이스2_최종_답변_텍스트_없으면_ValueError_발생(self) -> None:
        """케이스2: edited_answer / answer_draft / urgent_draft 모두 None → ValueError 발생.

        publish_final_answer_node는 세 필드를 OR로 순서대로 확인한다:
          final_answer = edited_answer or answer_draft or urgent_draft
        모두 None이면 빈 응답이 고객에게 전송될 위험이 있으므로 ValueError로 차단한다.
        """
        # 세 답변 필드 모두 None인 state
        state = OperationState(ticket_id="1001")

        with self.assertRaises(ValueError):
            nodes.publish_final_answer_node(state)


# ─── 20. human_review_node 케이스1/2 ─────────────────────────────────────────

class HumanReviewNodeTest(unittest.TestCase):
    """human_review_node 케이스1(approved), 케이스2(reject) 단위 테스트.

    LlmNodesStateUpdateTest에서는 decision="edit" 케이스만 확인했으므로
    approved / reject 두 케이스를 별도로 검증한다.
    human_review_node는 LLM 응답의 decision을 human_decision state에 그대로 저장한다.
    """

    def test_케이스1_approved_결정_human_decision_approved(self) -> None:
        """케이스1: LLM이 approved 결정 반환 → human_decision="approved".

        명확한 승인 케이스에서 human_decision이 "approved"로 저장되어야
        route_by_human_decision이 publish_final_answer_node로 분기한다.
        """
        state = OperationState(ticket_id="1001", query_text="결제 확인")

        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            mock_llm.return_value = HumanReviewResponse(
                decision="approved",
                reason="답변이 정확하고 근거가 충분함",
                edited_answer=None,  # approved 결정에서는 edited_answer 불필요
            )
            update = nodes.human_review_node(state)

        self.assertEqual(update["human_decision"], "approved")
        self.assertEqual(update["human_review"].decision, "approved")
        # approved 결정에서 edited_answer는 None이어야 한다
        self.assertIsNone(update["edited_answer"])

    def test_케이스2_reject_결정_human_decision_reject_reason_채워짐(self) -> None:
        """케이스2: LLM이 reject 결정 반환 → human_decision="reject", reason 채워짐.

        반려 케이스에서 human_decision이 "reject"로 저장되어야
        route_by_human_decision이 retry_routing_node로 분기한다.
        reason은 retry_routing_node에서 metadata["retry_reason"]으로 저장되어
        다음 query_router/analyze_ticket 프롬프트에 주입된다.
        """
        state = OperationState(ticket_id="1001", query_text="결제 확인")

        with patch.object(nodes, "invoke_structured_llm") as mock_llm:
            mock_llm.return_value = HumanReviewResponse(
                decision="reject",
                reason="근거 문서와 답변 내용이 불일치함",
                edited_answer=None,  # reject 결정에서는 edited_answer 불필요
            )
            update = nodes.human_review_node(state)

        self.assertEqual(update["human_decision"], "reject")
        self.assertEqual(update["human_review"].reason, "근거 문서와 답변 내용이 불일치함")


if __name__ == "__main__":
    unittest.main()
