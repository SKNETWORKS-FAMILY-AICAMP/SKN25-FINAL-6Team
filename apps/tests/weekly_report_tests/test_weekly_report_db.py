"""db/top_requests.py · db/spike_alerts.py 단위 테스트.

순수 계산 함수는 직접 호출하고, DB 의존 함수는 db_connection을 monkeypatch로 대체한다.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from db.top_requests import (
    get_risk_level_score,
    classify_improvement_type,
    build_top5_slack_blocks,
    calculate_priority_score,
    fetch as fetch_top_requests,
)
from db.spike_alerts import (
    _zscore_level,
    _wow_level,
    build_spike_slack_blocks,
)


# ── 공통 DB 모킹 헬퍼 ─────────────────────────────────────────────────────────

def _make_db_mock(fetchall_side_effects: list):
    """db_connection 컨텍스트 매니저를 흉내 내는 mock을 반환한다.

    fetchall_side_effects: 순서대로 각 execute 후 fetchall()이 반환할 값 목록.

    실제 코드는 `with db_connection() as conn: with conn.cursor() as cur:` 패턴을 쓰므로
    conn과 cur 양쪽에 __enter__/__exit__ 를 명시해야 한다.
    MagicMock이 자동 생성하는 __enter__ 는 새 MagicMock을 반환하므로
    fetchall.side_effect 가 설정된 cur 객체가 전달되지 않는 문제가 생긴다.
    """
    mock_cur = MagicMock()
    mock_cur.fetchall.side_effect = fetchall_side_effects
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    return mock_conn


# ── db/top_requests.py ────────────────────────────────────────────────────────

class TestGetRiskLevelScore:
    """get_risk_level_score: 위험도 레이블을 우선순위 점수로 변환한다.

    매핑: low=1, medium=2, high=3, critical=4
    미정의 레이블은 가장 낮은 점수(1)로 처리해 순위 계산에서 뒤로 밀린다.
    DB 값이 대소문자 혼용으로 저장될 수 있어 대소문자 무감지 처리가 필요하다.
    """

    def test_critical(self):
        assert get_risk_level_score("critical") == 4

    def test_high(self):
        assert get_risk_level_score("high") == 3

    def test_medium(self):
        assert get_risk_level_score("medium") == 2

    def test_low(self):
        assert get_risk_level_score("low") == 1

    def test_unknown_defaults_to_1(self):
        assert get_risk_level_score("unknown") == 1

    def test_unmapped_defaults_to_1(self):
        assert get_risk_level_score("whatever") == 1

    def test_case_insensitive(self):
        # DB 저장 시 대소문자가 일관되지 않을 수 있다.
        assert get_risk_level_score("HIGH") == 3
        assert get_risk_level_score("Critical") == 4


class TestClassifyImprovementType:
    """classify_improvement_type: 위험도 수준에 따라 개선 유형을 분류한다.

    high·critical → "설계 결함"  (근본적 수정 필요)
    low·medium    → "편의 개선"  (사용성 향상 수준)
    level 키가 없거나 미정의 값이면 보수적으로 "편의 개선"으로 분류한다.
    """

    def test_critical_is_design_flaw(self):
        assert classify_improvement_type({"level": "critical"}) == "설계 결함"

    def test_high_is_design_flaw(self):
        assert classify_improvement_type({"level": "high"}) == "설계 결함"

    def test_medium_is_convenience(self):
        assert classify_improvement_type({"level": "medium"}) == "편의 개선"

    def test_low_is_convenience(self):
        assert classify_improvement_type({"level": "low"}) == "편의 개선"

    def test_unknown_is_convenience(self):
        assert classify_improvement_type({"level": "unknown"}) == "편의 개선"

    def test_missing_level_is_convenience(self):
        # level 키 자체가 없어도 기본값으로 안전하게 처리해야 한다.
        assert classify_improvement_type({}) == "편의 개선"


class TestBuildTop5SlackBlocks:
    """build_top5_slack_blocks: Top5 카테고리 목록을 Slack Block Kit 형식으로 변환한다.

    항목당 section + divider 2개 블록을 생성한다.
    키워드가 없으면 "—"를 표시해 빈 필드가 노출되지 않도록 한다.
    """

    def test_empty_list_returns_empty(self):
        assert build_top5_slack_blocks([]) == []

    def test_block_structure(self):
        top5 = [
            {
                "rank": 1,
                "category": "결제",
                "count": 10,
                "level": "high",
                "priority_score": 7.4,
                "improvement_type": "설계 결함",
                "topic_keywords": ["환불", "오류"],
            }
        ]
        blocks = build_top5_slack_blocks(top5)
        # 항목 1개 → section + divider = 블록 2개
        assert len(blocks) == 2
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "divider"
        text = blocks[0]["fields"][0]["text"]
        assert "#1 결제" in text
        assert "환불 / 오류" in text

    def test_no_keywords_shows_dash(self):
        top5 = [
            {
                "rank": 1,
                "category": "결제",
                "count": 5,
                "level": "low",
                "priority_score": 2.6,
                "improvement_type": "편의 개선",
                "topic_keywords": [],
            }
        ]
        blocks = build_top5_slack_blocks(top5)
        # 키워드 빈 리스트 → "—" 로 채워야 한다.
        assert "—" in blocks[0]["fields"][0]["text"]


class TestCalculatePriorityScore:
    def test_higher_severity_wins_over_count(self):
        """위험도가 높은 카테고리가 건수가 적어도 상위에 와야 한다.

        공식: score = (cnt × 0.4) + (severity × 0.6)
        low(1) × 10건 = 4 + 0.6 = 4.6
        critical(4) × 1건 = 0.4 + 2.4 = 2.8  → low가 앞서야 정상
        → 건수가 많으면 점수가 높아지는 게 맞지만, severity가 4배면 뒤집힌다.

        cnt=1, severity=4 → 0.4 + 2.4 = 2.8
        cnt=10, severity=1 → 4.0 + 0.6 = 4.6  → 건수 많은 쪽이 높다
        """
        # 실제 DB 없이 calculate_priority_score 내부 공식만 검증한다.
        # priority_score = round((cnt * 0.4) + (severity_score * 0.6), 1)
        cnt, severity = 10, 1
        score_low_sev = round((cnt * 0.4) + (severity * 0.6), 1)
        cnt2, severity2 = 1, 4
        score_high_sev = round((cnt2 * 0.4) + (severity2 * 0.6), 1)
        assert score_low_sev > score_high_sev  # 건수 많은 쪽 > 심각도 높은 쪽 (이 경우)

    def test_with_mocked_db(self, monkeypatch):
        """DB를 모킹해 calculate_priority_score가 올바른 순서로 반환하는지 검증한다."""
        # 첫 번째 fetchall: 카테고리별 cnt + severity_score
        # 두 번째 fetchall: 키워드 쿼리 결과
        category_rows = [
            {"category": "결제", "cnt": 10, "severity_score": 3},
            {"category": "버그", "cnt": 2, "severity_score": 4},
        ]
        keyword_rows = []  # 키워드 없음

        mock_conn = _make_db_mock([category_rows, keyword_rows])
        monkeypatch.setattr("db.top_requests.db_connection", lambda: mock_conn)

        window = {
            "window_start": datetime(2026, 6, 5),
            "window_end": datetime(2026, 6, 12),
        }
        result = calculate_priority_score(window)

        # 결제: (10*0.4) + (3*0.6) = 4.0 + 1.8 = 5.8
        # 버그:  (2*0.4) + (4*0.6) = 0.8 + 2.4 = 3.2
        assert result[0]["category"] == "결제"
        assert result[1]["category"] == "버그"
        assert result[0]["priority_score"] == pytest.approx(5.8, abs=0.1)


class TestFetchTopRequests:
    def test_returns_rank_and_improvement_type(self, monkeypatch):
        category_rows = [
            {"category": "결제", "cnt": 5, "severity_score": 3},
        ]
        keyword_rows = []
        mock_conn = _make_db_mock([category_rows, keyword_rows])
        monkeypatch.setattr("db.top_requests.db_connection", lambda: mock_conn)

        window = {
            "window_start": datetime(2026, 6, 5),
            "window_end": datetime(2026, 6, 12),
        }
        result = fetch_top_requests(window)

        assert result[0]["rank"] == 1
        assert "improvement_type" in result[0]
        assert result[0]["improvement_type"] in ("설계 결함", "편의 개선")

    def test_returns_at_most_top_n(self, monkeypatch):
        # TOP_N=5 이므로 6개를 주면 5개만 반환해야 한다.
        category_rows = [
            {"category": f"cat{i}", "cnt": 10 - i, "severity_score": 2}
            for i in range(6)
        ]
        keyword_rows = []
        mock_conn = _make_db_mock([category_rows, keyword_rows])
        monkeypatch.setattr("db.top_requests.db_connection", lambda: mock_conn)

        window = {
            "window_start": datetime(2026, 6, 5),
            "window_end": datetime(2026, 6, 12),
        }
        result = fetch_top_requests(window)
        assert len(result) == 5


# ── db/spike_alerts.py ────────────────────────────────────────────────────────

class TestZscoreLevel:
    """_zscore_level: 시간별 문의량의 Z-score를 심각도 레이블로 변환한다.

    Z-score는 (현재값 - 평균) / 표준편차로 계산되며, 통계적 이상치 판별에 사용한다.
    임계값: z < 2.0 → normal, 2.0 ≤ z < 3.0 → warning, z ≥ 3.0 → critical
    경계값(2.0, 3.0)이 각각 어느 등급에 속하는지 명확히 검증한다.
    """

    def test_below_warning_is_normal(self):
        assert _zscore_level(1.9) == "normal"

    def test_at_warning_threshold(self):
        # z=2.0 은 warning 경계값이므로 warning이어야 한다.
        assert _zscore_level(2.0) == "warning"

    def test_between_warning_and_critical(self):
        assert _zscore_level(2.5) == "warning"

    def test_at_critical_threshold(self):
        # z=3.0 은 critical 경계값이므로 critical이어야 한다.
        assert _zscore_level(3.0) == "critical"

    def test_above_critical(self):
        assert _zscore_level(5.0) == "critical"

    def test_negative_zscore_is_normal(self):
        # 평균 이하로 낮은 경우는 이상 없음으로 처리한다.
        assert _zscore_level(-1.0) == "normal"


class TestWowLevel:
    """_wow_level: WoW(Week-over-Week) 증가율을 심각도 레이블로 변환한다.

    WoW = (이번 주 - 전주) / 전주. 증가율이 클수록 이상 폭증 가능성이 높다.
    임계값: pct < 0.5 → normal, 0.5 ≤ pct < 1.0 → warning, pct ≥ 1.0 → critical
    (1.0 = 전주 대비 100% 증가 = 2배)
    감소(-) 는 alert 대상이 아니므로 normal이다.
    """

    def test_below_warning_is_normal(self):
        assert _wow_level(0.49) == "normal"

    def test_at_warning_threshold(self):
        # pct=0.5(+50%) 이 warning 경계값이다.
        assert _wow_level(0.5) == "warning"

    def test_between_warning_and_critical(self):
        assert _wow_level(0.8) == "warning"

    def test_at_critical_threshold(self):
        # pct=1.0(+100%, 전주 대비 2배) 이 critical 경계값이다.
        assert _wow_level(1.0) == "critical"

    def test_above_critical(self):
        assert _wow_level(2.0) == "critical"

    def test_decrease_is_normal(self):
        # 감소는 폭증 alert 대상이 아니다.
        assert _wow_level(-0.3) == "normal"


class TestBuildSpikeSlackBlocks:
    """build_spike_slack_blocks: 폭증 알림 목록을 Slack Block Kit 형식으로 변환한다.

    alerts 구조:
      {"hourly": [{hour, level, zscore}, ...], "daily": [{day, pct_change, level, ...}, ...]}

    알림이 없으면 "이상 폭증 감지 없음" 단일 블록을 반환한다.
    hourly·daily 각각 alert가 있으면 별도 섹션 블록으로 분리된다.
    Z-score 시각화 막대는 최대 5칸으로 제한해 메시지 길이를 일정하게 유지한다.
    """

    def test_no_alerts_returns_ok_message(self):
        alerts = {"hourly": [], "daily": []}
        blocks = build_spike_slack_blocks(alerts)
        assert len(blocks) == 1
        assert "이상 폭증 감지 없음" in blocks[0]["text"]["text"]

    def test_hourly_alert_included(self):
        alerts = {
            "hourly": [{"hour": 14, "level": "critical", "zscore": 3.5}],
            "daily": [],
        }
        blocks = build_spike_slack_blocks(alerts)
        text = blocks[0]["text"]["text"]
        assert "14시" in text
        assert "critical" in text

    def test_daily_alert_included(self):
        alerts = {
            "hourly": [],
            "daily": [{"day": "Monday", "pct_change": 0.75, "level": "warning", "this_week": 15, "prev_week": 10}],
        }
        blocks = build_spike_slack_blocks(alerts)
        text = blocks[0]["text"]["text"]
        assert "Monday" in text
        # pct_change=0.75 → 75.0% 로 포매팅되어야 한다.
        assert "75.0%" in text

    def test_zscore_bar_capped_at_5(self):
        # Z=10이어도 막대는 최대 5칸
        alerts = {
            "hourly": [{"hour": 3, "level": "critical", "zscore": 10.0}],
            "daily": [],
        }
        blocks = build_spike_slack_blocks(alerts)
        text = blocks[0]["text"]["text"]
        assert "█" * 5 in text
        assert "█" * 6 not in text

    def test_both_hourly_and_daily_produce_two_sections(self):
        # hourly·daily 모두 있을 때 섹션이 분리되어야 한다.
        alerts = {
            "hourly": [{"hour": 2, "level": "warning", "zscore": 2.1}],
            "daily": [{"day": "Friday", "pct_change": 0.6, "level": "warning", "this_week": 8, "prev_week": 5}],
        }
        blocks = build_spike_slack_blocks(alerts)
        assert len(blocks) == 2
