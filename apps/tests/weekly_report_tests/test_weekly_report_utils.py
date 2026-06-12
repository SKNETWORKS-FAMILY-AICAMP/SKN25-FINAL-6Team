"""utils/stats.py · utils/date_range.py · utils/labels.py 단위 테스트.

모든 함수가 순수 함수이므로 외부 의존성 없이 실행된다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from utils.stats import clamp_days, build_window, rate, safe_average
from utils.date_range import get_window, get_previous_window
from utils.labels import translate_label, translate_value, localized_rows


# ── utils/stats.py ────────────────────────────────────────────────────────────

class TestClampDays:
    """clamp_days: 입력 일수를 [MIN_DAYS=1, MAX_DAYS=365] 범위로 제한한다.

    Airflow DAG 파라미터와 환경변수 모두 문자열로 전달될 수 있어 형변환 내성도 함께 검증한다.
    """

    def test_below_min_returns_min(self):
        assert clamp_days(0) == 1

    def test_above_max_returns_max(self):
        assert clamp_days(400) == 365

    def test_within_range_unchanged(self):
        assert clamp_days(7) == 7

    def test_accepts_string_input(self):
        # Airflow 환경변수는 문자열로 전달되므로 str 입력도 처리해야 한다.
        assert clamp_days("14") == 14

    def test_accepts_float_input(self):
        # float는 int로 내림 변환(truncate) 후 클램핑한다.
        assert clamp_days(7.9) == 7

    def test_custom_min_max(self):
        assert clamp_days(3, min_days=5, max_days=10) == 5
        assert clamp_days(15, min_days=5, max_days=10) == 10


class TestBuildWindow:
    """build_window: days를 받아 {days, window_start, window_end} 딕셔너리를 반환한다.

    now 파라미터를 고정하면 결정론적 테스트가 가능하다.
    now=None이면 datetime.now()를 기준으로 계산한다.
    """

    def test_returns_required_keys(self):
        w = build_window(7)
        assert {"days", "window_start", "window_end"} <= w.keys()

    def test_window_span_matches_days(self):
        now = datetime(2026, 6, 12, 10, 0, 0)
        w = build_window(7, now=now)
        assert w["window_end"] == now
        assert w["window_start"] == now - timedelta(days=7)
        assert w["days"] == 7

    def test_uses_current_time_when_now_is_none(self):
        # 호출 전후 시각으로 window_end 범위를 확인한다.
        before = datetime.now()
        w = build_window(3)
        after = datetime.now()
        assert before <= w["window_end"] <= after

    def test_clamps_days_inside(self):
        # days=0 은 MIN_DAYS=1 로 클램핑된다.
        w = build_window(0)
        assert w["days"] == 1


class TestRate:
    """rate: numerator / denominator 비율을 반환한다.

    DB 집계에서 행이 없으면 COUNT(*) 가 0 또는 NULL로 반환될 수 있으므로
    0·None 입력 모두 안전하게 0.0으로 처리해야 한다.
    """

    def test_normal_case(self):
        assert rate(3, 10) == pytest.approx(0.3)

    def test_denominator_zero_returns_zero(self):
        # ZeroDivisionError 대신 0.0을 반환해 호출부에서 별도 방어 코드가 불필요하다.
        assert rate(5, 0) == 0.0

    def test_denominator_none_returns_zero(self):
        # SQL LEFT JOIN 집계에서 대응 행이 없으면 NULL(Python None)로 온다.
        assert rate(5, None) == 0.0

    def test_numerator_none_treats_as_zero(self):
        assert rate(None, 10) == 0.0

    def test_both_none_returns_zero(self):
        assert rate(None, None) == 0.0

    def test_full_coverage(self):
        assert rate(10, 10) == pytest.approx(1.0)


class TestSafeAverage:
    """safe_average: None을 제거한 뒤 평균을 반환한다.

    유효값이 하나도 없으면 0이 아닌 None을 반환해, 호출부에서 '데이터 없음'과
    '평균이 실제로 0'을 구분할 수 있도록 한다.
    """

    def test_empty_list_returns_none(self):
        # 빈 리스트 = 조회 결과 자체가 없음 → None 반환
        assert safe_average([]) is None

    def test_all_none_returns_none(self):
        # 값이 전부 NULL = 파싱 실패 상황 → None 반환
        assert safe_average([None, None]) is None

    def test_filters_none_and_averages(self):
        assert safe_average([None, 10.0, None, 20.0]) == pytest.approx(15.0)

    def test_single_value(self):
        assert safe_average([42.0]) == pytest.approx(42.0)

    def test_all_same(self):
        assert safe_average([5, 5, 5]) == pytest.approx(5.0)


# ── utils/date_range.py ───────────────────────────────────────────────────────

class TestGetWindow:
    """get_window: build_window의 공개 래퍼. 기본 days=7, 반환 형태는 동일하다.

    date_range 모듈은 주간 리포트 전반에서 윈도우 기준점으로 사용되므로
    기본값과 클램핑이 정확해야 한다.
    """

    def test_returns_window_dict_with_correct_keys(self):
        w = get_window(7)
        assert "days" in w and "window_start" in w and "window_end" in w

    def test_default_days_is_7(self):
        # 인자 없이 호출하면 7일 윈도우가 기본값이다.
        w = get_window()
        assert w["days"] == 7

    def test_clamps_days(self):
        # 0일은 1일로 클램핑
        w = get_window(0)
        assert w["days"] == 1

    def test_now_parameter_fixes_reference_time(self):
        # now를 고정하면 결정론적으로 window_start 날짜를 검증할 수 있다.
        now = datetime(2026, 6, 12, 0, 0, 0)
        w = get_window(7, now=now)
        assert w["window_end"] == now
        assert w["window_start"] == datetime(2026, 6, 5, 0, 0, 0)


class TestGetPreviousWindow:
    """get_previous_window: current 윈도우 바로 직전 동일 기간을 반환한다.

    전주 대비 증감 계산(WoW)에 사용하므로 두 기간이 정확히 붙어 있어야 한다.
    """

    def test_previous_window_end_equals_current_start(self):
        # 두 window가 겹치거나 빠지지 않아야 한다.
        now = datetime(2026, 6, 12, 0, 0, 0)
        current = get_window(7, now=now)
        previous = get_previous_window(current)
        assert previous["window_end"] == current["window_start"]

    def test_previous_window_same_days(self):
        # 기간 길이는 현재 윈도우와 동일해야 공정한 WoW 비교가 된다.
        current = get_window(7)
        previous = get_previous_window(current)
        assert previous["days"] == current["days"]

    def test_previous_window_span(self):
        now = datetime(2026, 6, 12, 0, 0, 0)
        current = get_window(7, now=now)
        previous = get_previous_window(current)
        assert previous["window_start"] == datetime(2026, 5, 29, 0, 0, 0)
        assert previous["window_end"] == datetime(2026, 6, 5, 0, 0, 0)


# ── utils/labels.py ───────────────────────────────────────────────────────────

class TestTranslateLabel:
    """translate_label: DB 컬럼명을 한국어 표시명으로 변환한다.

    COLUMN_LABELS 에 없는 키는 원본 문자열을 그대로 반환해
    매핑 누락 시에도 데이터가 보이도록 한다.
    """

    def test_known_label(self):
        assert translate_label("ticket_id") == "문의 번호"

    def test_unknown_label_returns_original(self):
        # 매핑 미정의 키 → 원본 반환(누락 방어)
        assert translate_label("unknown_key_xyz") == "unknown_key_xyz"

    def test_risk_level(self):
        assert translate_label("risk_level") == "위험도"


class TestTranslateValue:
    """translate_value: DB에서 가져온 값을 PDF·Slack 출력용 한국어로 변환한다.

    번역 우선순위:
      1. None·빈문자열 → "-"
      2. bool → "예"/"아니오"
      3. key가 TRANSLATABLE_KEYS에 있으면 VALUE_LABELS 조회
      4. key="column" 이면 COLUMN_LABELS 조회(값을 컬럼명처럼 취급)
      5. key 없어도 VALUE_LABELS에 있으면 번역
      6. 모두 해당 없으면 원본 반환
    """

    def test_none_returns_dash(self):
        # PDF 셀에 None이 찍히면 렌더링 오류 발생 → 대시로 대체
        assert translate_value(None) == "-"

    def test_empty_string_returns_dash(self):
        assert translate_value("") == "-"

    def test_true_returns_yes(self):
        assert translate_value(True) == "예"

    def test_false_returns_no(self):
        assert translate_value(False) == "아니오"

    def test_translatable_key_high(self):
        # risk_level 은 TRANSLATABLE_KEYS에 포함 → VALUE_LABELS 에서 번역
        assert translate_value("high", key="risk_level") == "높음"

    def test_translatable_key_critical(self):
        assert translate_value("critical", key="risk_level") == "매우 높음"

    def test_column_key_uses_column_labels(self):
        # key="column" 이면 값 자체를 컬럼명으로 간주해 COLUMN_LABELS 에서 번역
        assert translate_value("ticket_id", key="column") == "문의 번호"

    def test_value_in_value_labels_without_key(self):
        # key 없이도 VALUE_LABELS에 정확히 있으면 번역(범용 폴백)
        assert translate_value("unknown") == "확인 필요"

    def test_unknown_value_without_key_returns_original(self):
        # 매핑 완전 미정의 → 원본 그대로 반환해 데이터 소실 방지
        assert translate_value("totally_unmapped_value") == "totally_unmapped_value"

    def test_comma_separated_values(self):
        # "high, critical" 같은 복합 값도 각각 번역해야 한다.
        result = translate_value("high, critical", key="risk_level")
        assert result == "높음, 매우 높음"


class TestLocalizedRows:
    """localized_rows: 행 목록의 키·값을 모두 한국어로 변환해 새 리스트로 반환한다.

    PDF 테이블 헤더와 셀 내용을 동시에 한국어화하는 진입점이다.
    """

    def test_translates_keys_and_values(self):
        rows = [{"risk_level": "high", "ticket_id": 1}]
        result = localized_rows(rows)
        assert result[0]["위험도"] == "높음"
        assert result[0]["문의 번호"] == 1

    def test_empty_rows(self):
        assert localized_rows([]) == []

    def test_does_not_mutate_original(self):
        # 원본 딕셔너리를 직접 수정하면 상위 파이프라인 데이터가 오염된다.
        original = [{"risk_level": "low"}]
        localized_rows(original)
        assert "risk_level" in original[0]
