"""ai/row_interpret.py · ai/actions.py 단위 테스트.

LLM 호출은 monkeypatch로 차단하거나 환경변수를 비워 fallback 경로를 검증한다.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from ai.row_interpret import (
    _fallback_row_interpretation,
    generate_review_row_interpretations,
    ReviewRowInterpretationItem,
    ReviewRowInterpretationPayload,
)
from ai.actions import (
    _fallback,
    _build_user_prompt,
    generate_ai_actions,
    is_fallback_ai_actions,
    AiRecommendedActions,
    ActionItem,
)


# ── ai/row_interpret.py ───────────────────────────────────────────────────────

class TestFallbackRowInterpretation:
    """_fallback_row_interpretation: LLM 없이 규칙 기반으로 행 해석 문장을 생성한다.

    LLM 호출 실패·환경변수 미설정 시 폴백으로 사용하므로
    어떤 입력에도 반드시 비어 있지 않은 문자열을 반환해야 한다.
    """

    def test_all_fields_present(self):
        row = {
            "title": "결제 오류 문의",
            "category": "결제",
            "risk_level": "high",
            "routing_target": "human_review",
            "sentiment": "negative",
        }
        result = _fallback_row_interpretation(row)
        assert "결제 오류 문의" in result
        assert "결제" in result
        assert "high" in result
        assert "negative" in result
        assert "human_review" in result

    def test_missing_fields_use_defaults(self):
        # 빈 딕셔너리를 넣어도 의미 있는 한국어 문장이 생성되어야 한다.
        result = _fallback_row_interpretation({})
        assert "제목 없는 문의" in result
        assert "분류 미확인" in result
        assert "위험도 미확인" in result
        assert "후속 처리 미정" in result

    def test_no_sentiment_field_omits_sentiment_text(self):
        row = {"title": "환불 요청", "category": "환불", "risk_level": "medium", "routing_target": "auto"}
        result = _fallback_row_interpretation(row)
        # sentiment가 없으면 "이용자 반응은" 문구가 포함되지 않아야 한다.
        assert "이용자 반응은" not in result

    def test_empty_sentiment_omits_sentiment_text(self):
        # 빈문자열 sentiment도 없음으로 취급한다.
        row = {"sentiment": ""}
        result = _fallback_row_interpretation(row)
        assert "이용자 반응은" not in result

    def test_returns_string(self):
        assert isinstance(_fallback_row_interpretation({}), str)


class TestGenerateReviewRowInterpretations:
    """generate_review_row_interpretations: 검토 행마다 LLM 해석 문자열을 붙여 반환한다.

    LLM 호출 경로와 폴백 경로 모두 테스트한다.
    LLM 테스트는 invoke_structured_llm을 monkeypatch로 교체해 실제 API를 호출하지 않는다.
    """

    def test_empty_rows_returns_empty(self):
        assert generate_review_row_interpretations([]) == []

    def test_no_llm_env_uses_fallback(self, monkeypatch):
        # LLM 환경변수가 없으면 fallback 경로를 탄다.
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        rows = [{"analysis_id": 1, "ticket_id": 10, "title": "오류", "risk_level": "high"}]
        result = generate_review_row_interpretations(rows)

        assert len(result) == 1
        assert result[0]["analysis_id"] == 1
        assert result[0]["ticket_id"] == 10
        assert isinstance(result[0]["interpretation"], str)
        assert len(result[0]["interpretation"]) > 0

    def test_llm_success_maps_interpretations(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "test-model")
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        fake_response = ReviewRowInterpretationPayload(
            items=[
                ReviewRowInterpretationItem(
                    analysis_id=1,
                    ticket_id=10,
                    interpretation="LLM이 생성한 해석입니다.",
                )
            ]
        )
        monkeypatch.setattr("ai.row_interpret.invoke_structured_llm", lambda **kwargs: fake_response)

        rows = [{"analysis_id": 1, "ticket_id": 10, "title": "오류", "risk_level": "high"}]
        result = generate_review_row_interpretations(rows)

        assert result[0]["interpretation"] == "LLM이 생성한 해석입니다."

    def test_llm_exception_falls_back(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "test-model")
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        def _raise(**kwargs):
            raise RuntimeError("LLM 타임아웃")

        monkeypatch.setattr("ai.row_interpret.invoke_structured_llm", _raise)

        rows = [{"analysis_id": 1, "ticket_id": 10, "title": "오류", "risk_level": "high"}]
        result = generate_review_row_interpretations(rows)

        # 예외 발생해도 결과는 반환해야 한다.
        assert len(result) == 1
        assert isinstance(result[0]["interpretation"], str)

    def test_llm_missing_key_fills_fallback(self, monkeypatch):
        """LLM 응답에서 일부 행의 키가 누락되면 해당 행을 fallback으로 채운다."""
        monkeypatch.setenv("LLM_MODEL", "test-model")
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        # row(analysis_id=2)에 대한 해석이 응답에 없다.
        fake_response = ReviewRowInterpretationPayload(
            items=[
                ReviewRowInterpretationItem(analysis_id=1, ticket_id=10, interpretation="해석1"),
            ]
        )
        monkeypatch.setattr("ai.row_interpret.invoke_structured_llm", lambda **kwargs: fake_response)

        rows = [
            {"analysis_id": 1, "ticket_id": 10, "title": "row1"},
            {"analysis_id": 2, "ticket_id": 20, "title": "row2"},
        ]
        result = generate_review_row_interpretations(rows)

        assert result[0]["interpretation"] == "해석1"
        # 두 번째 행은 fallback으로 채워져야 한다.
        assert isinstance(result[1]["interpretation"], str)
        assert result[1]["interpretation"] != ""


# ── ai/actions.py ─────────────────────────────────────────────────────────────

class TestFallback:
    """_fallback: LLM 호출 실패 시 반환하는 최소 구조의 긴급 폴백 응답을 생성한다.

    운영자가 Slack에서 오류 원인을 바로 확인할 수 있도록
    reason 필드에 오류 메시지를 그대로 포함해야 한다.
    """

    def test_structure(self):
        result = _fallback("테스트 오류")
        assert "headline" in result
        assert "actions" in result
        assert isinstance(result["actions"], list)
        assert len(result["actions"]) >= 1

    def test_reason_in_action(self):
        # 오류 내용이 reason에 그대로 전달되어야 운영자가 원인을 파악할 수 있다.
        result = _fallback("LLM 연결 실패")
        assert result["actions"][0]["reason"] == "LLM 연결 실패"

    def test_rank_and_category(self):
        # 폴백 항목은 rank=1, category="시스템"으로 고정된다.
        result = _fallback("오류")
        assert result["actions"][0]["rank"] == 1
        assert isinstance(result["actions"][0]["category"], str)
        assert result["actions"][0]["category"]
        assert result["actions"][0]["category"] == "시스템"
        assert "다시 실행하세요" in result["actions"][0]["action"]


    def test_detects_fallback_payload(self):
        assert is_fallback_ai_actions(_fallback("?ㅻ쪟")) is True

    def test_non_fallback_payload_returns_false(self):
        assert is_fallback_ai_actions(
            {
                "headline": "Weekly summary",
                "actions": [{"rank": 1, "category": "결제", "action": "Do X", "reason": "Because"}],
            }
        ) is False


class TestBuildUserPrompt:
    """_build_user_prompt: report payload를 LLM에 전달할 자연어 프롬프트로 변환한다.

    summary 키는 빌드 경로에 따라 total_count 또는 analysis_count 중 하나를 사용한다.
    category_distribution 은 list[{label, value}] 또는 dict 두 형태 모두 지원한다.
    """

    def _sample_payload(self) -> dict[str, Any]:
        return {
            "summary": {"total_count": 100, "prev_total": 80},
            "spike_alerts": {
                "hourly": [{"hour": 14, "level": "critical"}],
                "by_category": [],
            },
            "category_distribution": [
                {"label": "결제", "value": 40},
                {"label": "버그", "value": 20},
            ],
            "top5_improvements": [
                {"category": "결제", "count": 40, "improvement_type": "설계 결함"},
                {"category": "버그", "count": 20, "improvement_type": "편의 개선"},
            ],
        }

    def test_contains_total_count(self):
        prompt = _build_user_prompt(self._sample_payload())
        assert "100" in prompt
        assert "[주간 데이터]" in prompt

    def test_contains_pct_change(self):
        prompt = _build_user_prompt(self._sample_payload())
        # 100건 / 80건 = +25%
        assert "+25.0%" in prompt

    def test_contains_critical_hour(self):
        # 폭증 발생 시각이 프롬프트에 포함되어야 LLM이 맥락을 파악할 수 있다.
        prompt = _build_user_prompt(self._sample_payload())
        assert "14" in prompt

    def test_list_category_distribution(self):
        prompt = _build_user_prompt(self._sample_payload())
        assert "결제" in prompt

    def test_dict_category_distribution(self):
        # category_distribution이 dict 형태로 오는 빌드 경로도 처리해야 한다.
        payload = self._sample_payload()
        payload["category_distribution"] = {"결제": 40, "버그": 20}
        prompt = _build_user_prompt(payload)
        assert "결제" in prompt

    def test_no_prev_total_zero_pct_change(self):
        payload = self._sample_payload()
        payload["summary"]["prev_total"] = 0
        prompt = _build_user_prompt(payload)
        # 전주 0건이면 pct_change=0.0 → "+0.0%"
        assert "+0.0%" in prompt

    def test_uses_analysis_count_fallback(self):
        # build_report_payload 경로에서는 analysis_count 키를 사용한다.
        payload = {
            "summary": {"analysis_count": 50, "prev_total": 0},
            "spike_alerts": {},
            "category_distribution": [],
            "top5_improvements": [],
        }
        prompt = _build_user_prompt(payload)
        assert "50" in prompt
        assert "category 값도 한국어로 작성하라." in prompt


class TestGenerateAiActions:
    """generate_ai_actions: 주간 리포트 payload를 받아 AI 권고 액션 딕셔너리를 반환한다.

    반환 형식: {"headline": str, "actions": [{rank, category, action, reason}, ...]}
    LLM 호출 성공·실패·환경변수 미설정 세 가지 경로를 모두 검증한다.
    """

    def test_no_llm_returns_fallback(self, monkeypatch):
        # 환경변수 미설정 → LLM 초기화 없이 폴백 구조 반환
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        result = generate_ai_actions({"summary": {}, "spike_alerts": {}, "category_distribution": [], "top5_improvements": []})

        assert "headline" in result
        assert "actions" in result
        assert result["headline"] == "AI 권장 액션을 생성하지 못했습니다."

    def test_llm_success_returns_model_dump(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "test-model")
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        fake_response = AiRecommendedActions(
            headline="이번 주 요약",
            actions=[
                ActionItem(rank=1, category="결제", action="결제 오류 처리 강화", reason="결제 30건 급증")
            ],
        )
        # Pydantic 모델을 반환하는 LLM 호출을 mock으로 교체한다.
        monkeypatch.setattr("ai.actions.invoke_structured_llm", lambda **kwargs: fake_response)

        payload = {"summary": {"total_count": 30, "prev_total": 10}, "spike_alerts": {}, "category_distribution": [], "top5_improvements": []}
        result = generate_ai_actions(payload)

        assert result["headline"] == "이번 주 요약"
        assert result["actions"][0]["category"] == "결제"

    def test_llm_exception_returns_fallback(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "test-model")
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        def _raise(**kwargs):
            raise ConnectionError("API 연결 실패")

        monkeypatch.setattr("ai.actions.invoke_structured_llm", _raise)

        result = generate_ai_actions({"summary": {}, "spike_alerts": {}, "category_distribution": [], "top5_improvements": []})

        assert "headline" in result
        assert len(result["actions"]) >= 1
        # 오류 내용이 reason에 포함되어야 운영자가 Slack에서 원인을 확인할 수 있다.
        assert "API 연결 실패" in result["actions"][0]["reason"]
