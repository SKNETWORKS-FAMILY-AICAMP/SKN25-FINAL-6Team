"""build/distributions.py · build/review_rows.py 단위 테스트.

순수 함수 위주이므로 외부 의존성 없이 실행된다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from build.distributions import normalize_text, distribution, format_change
from build.review_rows import pick_review_rows, build_analysis_rows_payload


# ── build/distributions.py ───────────────────────────────────────────────────

class TestNormalizeText:
    """normalize_text: 분포 집계 시 DB에서 온 값을 안전한 문자열로 변환한다.

    None·빈값은 "unknown"으로 대체해 집계 키가 깨지지 않도록 한다.
    fallback 파라미터로 호출부가 대체값을 커스터마이징할 수 있다.
    """

    def test_none_returns_fallback(self):
        assert normalize_text(None) == "unknown"

    def test_empty_string_returns_fallback(self):
        assert normalize_text("") == "unknown"

    def test_whitespace_only_returns_fallback(self):
        # 공백만 있는 경우도 빈값으로 간주한다.
        assert normalize_text("   ") == "unknown"

    def test_normal_string_stripped(self):
        assert normalize_text("  high  ") == "high"

    def test_custom_fallback(self):
        assert normalize_text(None, fallback="") == ""

    def test_zero_integer(self):
        # 0은 falsy지만 "0"이라는 유효한 값으로 처리해야 한다.
        assert normalize_text(0) == "0"


class TestDistribution:
    """distribution: 행 목록을 집계해 [{label, value}] 형태의 분포 리스트를 반환한다.

    Slack·PDF 차트 렌더링에 직접 사용되므로 정렬과 누락값 처리가 정확해야 한다.
    정렬 기준: 건수 내림차순, 동점이면 label 알파벳 오름차순(재현 가능한 순서 보장).
    """

    def test_single_category(self):
        rows = [{"category": "payment"}, {"category": "payment"}]
        result = distribution(rows, "category")
        assert result == [{"label": "payment", "value": 2}]

    def test_sorted_by_count_descending(self):
        rows = [
            {"category": "refund"},
            {"category": "payment"},
            {"category": "payment"},
            {"category": "payment"},
        ]
        result = distribution(rows, "category")
        assert result[0]["label"] == "payment"
        assert result[1]["label"] == "refund"

    def test_tie_sorted_alphabetically(self):
        rows = [{"category": "z_cat"}, {"category": "a_cat"}]
        result = distribution(rows, "category")
        # 동점일 때 알파벳 오름차순
        assert result[0]["label"] == "a_cat"
        assert result[1]["label"] == "z_cat"

    def test_none_value_becomes_unknown(self):
        # DB에서 카테고리가 NULL인 행도 집계에 포함되어야 한다.
        rows = [{"category": None}]
        result = distribution(rows, "category")
        assert result[0]["label"] == "unknown"

    def test_empty_rows(self):
        assert distribution([], "category") == []

    def test_missing_key_becomes_unknown(self):
        # 지정한 컬럼 자체가 없는 행도 unknown으로 처리한다.
        rows = [{"other": "x"}]
        result = distribution(rows, "category")
        assert result[0]["label"] == "unknown"


class TestFormatChange:
    """format_change(current, previous): 전주 대비 변화를 문자열로 표현한다.

    반환 형식:
      - previous == 0 && current == 0  →  "0"  (변화 없음)
      - previous == 0 && current  > 0  →  "+N"  (신규 발생, % 계산 불가)
      - 그 외                          →  "+N.N%" / "-N.N%"
    """

    def test_both_zero(self):
        assert format_change(0, 0) == "0"

    def test_previous_zero_current_positive(self):
        # 전주 데이터가 없고 이번 주만 있으면 신규 발생으로 표시
        assert format_change(5, 0) == "+5"

    def test_increase(self):
        result = format_change(120, 100)
        assert result == "+20.0%"

    def test_decrease(self):
        result = format_change(80, 100)
        assert result == "-20.0%"

    def test_no_change(self):
        result = format_change(100, 100)
        assert result == "+0.0%"


# ── build/review_rows.py ─────────────────────────────────────────────────────

def _make_row(**kwargs) -> dict:
    """플래그 조건을 하나도 충족하지 않는 기본 행을 반환한다.

    kwargs로 특정 필드를 오버라이드해 플래그 조건을 개별 테스트할 수 있다.
    모든 필드는 build_analysis_rows_payload가 요구하는 최소 스키마를 충족한다.
    """
    base = {
        "analysis_id": 1,
        "ticket_id": 1,
        "title": "test",
        "risk_level": "low",
        "routing_target": "auto_reply",
        "sentiment": "neutral",
        "summary": "정상 요약",
        "category": "general",
        "analyzed_at": datetime(2026, 6, 12),
    }
    base.update(kwargs)
    return base


class TestPickReviewRows:
    """pick_review_rows: 주의 깊게 검토해야 할 행을 골라낸다.

    플래그 조건(우선순위 없이 OR):
      - risk_level: "high" 또는 "critical"
      - routing_target: "urgent_alert" 또는 "human_review"
      - sentiment: "negative" 또는 "very_negative"
      - summary: None 또는 빈문자열(AI 요약 실패)

    플래그 행이 없으면 앞 limit개를 그대로 반환한다(최소 표시 보장).
    """

    def test_flags_high_risk(self):
        rows = [_make_row(risk_level="high"), _make_row()]
        result = pick_review_rows(rows)
        assert len(result) == 1
        assert result[0]["risk_level"] == "high"

    def test_flags_critical_risk(self):
        rows = [_make_row(risk_level="critical"), _make_row()]
        result = pick_review_rows(rows)
        assert result[0]["risk_level"] == "critical"

    def test_flags_urgent_alert_routing(self):
        rows = [_make_row(routing_target="urgent_alert"), _make_row()]
        result = pick_review_rows(rows)
        assert result[0]["routing_target"] == "urgent_alert"

    def test_flags_human_review_routing(self):
        rows = [_make_row(routing_target="human_review"), _make_row()]
        result = pick_review_rows(rows)
        assert result[0]["routing_target"] == "human_review"

    def test_flags_negative_sentiment(self):
        rows = [_make_row(sentiment="negative"), _make_row()]
        result = pick_review_rows(rows)
        assert result[0]["sentiment"] == "negative"

    def test_flags_very_negative_sentiment(self):
        rows = [_make_row(sentiment="very_negative"), _make_row()]
        result = pick_review_rows(rows)
        assert result[0]["sentiment"] == "very_negative"

    def test_flags_blank_summary(self):
        rows = [_make_row(summary=""), _make_row()]
        result = pick_review_rows(rows)
        assert result[0]["summary"] == ""

    def test_flags_none_summary(self):
        rows = [_make_row(summary=None), _make_row()]
        result = pick_review_rows(rows)
        assert result[0]["summary"] is None

    def test_fallback_when_no_flags(self):
        # 플래그 행이 없으면 앞 limit개를 그대로 반환한다.
        rows = [_make_row(ticket_id=i) for i in range(5)]
        result = pick_review_rows(rows, limit=3)
        assert len(result) == 3

    def test_respects_limit_on_flagged(self):
        rows = [_make_row(risk_level="high", ticket_id=i) for i in range(20)]
        result = pick_review_rows(rows, limit=5)
        assert len(result) == 5

    def test_empty_rows(self):
        assert pick_review_rows([]) == []


class TestBuildAnalysisRowsPayload:
    """build_analysis_rows_payload: DB 행 목록을 JSON 직렬화 가능한 페이로드로 변환한다.

    datetime 객체는 ISO 8601 문자열로 변환한다. 변환하지 않으면
    json.dumps 단계에서 TypeError가 발생한다.
    """

    def test_required_keys_present(self):
        row = _make_row()
        result = build_analysis_rows_payload([row])
        assert len(result) == 1
        item = result[0]
        for key in ("analysis_id", "ticket_id", "title", "category", "risk_level", "routing_target"):
            assert key in item

    def test_analyzed_at_converted_to_isoformat(self):
        row = _make_row(analyzed_at=datetime(2026, 6, 12, 9, 0, 0))
        result = build_analysis_rows_payload([row])
        assert result[0]["analyzed_at"] == "2026-06-12T09:00:00"

    def test_analyzed_at_none_stays_none(self):
        row = _make_row(analyzed_at=None)
        result = build_analysis_rows_payload([row])
        assert result[0]["analyzed_at"] is None

    def test_empty_rows(self):
        assert build_analysis_rows_payload([]) == []

    def test_no_extra_keys(self):
        # 원본 행의 analyzed_at(datetime 객체)이 payload에 남으면 JSON 직렬화에 실패한다.
        row = _make_row(analyzed_at=datetime(2026, 6, 12))
        result = build_analysis_rows_payload([row])
        assert isinstance(result[0]["analyzed_at"], str)
