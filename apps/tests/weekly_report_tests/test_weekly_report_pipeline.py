"""db/metrics.py · db/analysis.py · output/pdf.py · report.py 단위 테스트.

DB 의존 함수는 db_connection을 monkeypatch로 대체한다.
PDF 렌더러(xhtml2pdf)와 Slack·LLM은 monkeypatch로 차단한다.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# xhtml2pdf가 로컬에 설치되지 않아도 테스트가 실행될 수 있도록
# 임포트 전에 sys.modules에 stub을 등록한다.
if "xhtml2pdf" not in sys.modules:
    _xhtml2pdf_stub = types.ModuleType("xhtml2pdf")
    _pisa_stub = types.ModuleType("xhtml2pdf.pisa")
    _pisa_stub.CreatePDF = MagicMock(return_value=MagicMock(err=0))
    _xhtml2pdf_stub.pisa = _pisa_stub
    sys.modules["xhtml2pdf"] = _xhtml2pdf_stub
    sys.modules["xhtml2pdf.pisa"] = _pisa_stub


_WINDOW = {
    "window_start": datetime(2026, 6, 5),
    "window_end": datetime(2026, 6, 12),
    "days": 7,
}


# ── db/metrics.py ─────────────────────────────────────────────────────────────

class TestFetchMetrics:
    """db.metrics.fetch: 7개 KPI + 카테고리별 건수를 반환한다.

    DB 연결을 모킹해 SQL 실행 없이 반환값 구조와 비율 계산을 검증한다.
    """

    def _make_metrics_mock(self):
        # 5개 쿼리 순서: coverage, draft, final_resp, safety, category_rows
        fetchone_effects = [
            {"total_tickets": 10, "responded_tickets": 8, "draft_tickets": 6, "analyzed_tickets": 9},
            {"draft_count": 7, "draft_ticket_count": 6},
            {"final_response_ticket_count": 8},
            {"safety_check_count": 5},
        ]
        fetchall_effects = [
            [{"category": "결제", "count": 4}, {"category": "버그", "count": 6}],
        ]
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = fetchone_effects
        mock_cur.fetchall.side_effect = fetchall_effects
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn

    def test_returns_all_kpi_keys(self, monkeypatch):
        monkeypatch.setattr("db.metrics.db_connection", lambda: self._make_metrics_mock())
        from db.metrics import fetch
        result = fetch(_WINDOW)
        for key in (
            "response_rate", "analysis_coverage_rate", "draft_coverage_rate",
            "draft_ticket_rate", "final_response_ticket_rate",
            "draft_count", "safety_check_count", "total_tickets", "category_counts",
        ):
            assert key in result, f"누락된 키: {key}"

    def test_response_rate_calculated_correctly(self, monkeypatch):
        monkeypatch.setattr("db.metrics.db_connection", lambda: self._make_metrics_mock())
        from db.metrics import fetch
        result = fetch(_WINDOW)
        # responded=8 / total=10 = 0.8
        assert result["response_rate"] == pytest.approx(0.8)

    def test_category_counts_returned(self, monkeypatch):
        monkeypatch.setattr("db.metrics.db_connection", lambda: self._make_metrics_mock())
        from db.metrics import fetch
        result = fetch(_WINDOW)
        assert len(result["category_counts"]) == 2
        assert result["category_counts"][0]["category"] == "결제"

    def test_zero_total_tickets_no_division_error(self, monkeypatch):
        """total=0일 때 rate()가 0.0을 반환하고 ZeroDivisionError가 없어야 한다."""
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            {"total_tickets": 0, "responded_tickets": 0, "draft_tickets": 0, "analyzed_tickets": 0},
            {"draft_count": 0, "draft_ticket_count": 0},
            {"final_response_ticket_count": 0},
            {"safety_check_count": 0},
        ]
        mock_cur.fetchall.side_effect = [[]]
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("db.metrics.db_connection", lambda: mock_conn)

        from db.metrics import fetch
        result = fetch(_WINDOW)
        assert result["response_rate"] == 0.0
        assert result["total_tickets"] == 0


# ── db/analysis.py ────────────────────────────────────────────────────────────

class TestFetchAnalysisRows:
    """db.analysis.fetch_analysis_rows: ticket_analysis + qa_ticket + insight 조인 결과를 반환한다."""

    def test_returns_list_of_dicts(self, monkeypatch):
        rows = [
            {
                "analysis_id": 1, "ticket_id": 100, "category": "결제",
                "responder_type": "bot", "enriched_query": "결제 오류",
                "risk_level": "high", "sentiment": "negative",
                "routing_target": "human_review", "summary": "요약",
                "analyzed_at": datetime(2026, 6, 10),
                "title": "결제 안됨", "status": "open", "source_type": "web",
                "inquiry_created_at": datetime(2026, 6, 9), "nickname": "user1",
                "insight_id": None, "content_summary": None,
                "insight_category": None, "insight_sentiment": None,
                "insight_risk_level": None, "pattern_risk_level": None,
                "insight_created_at": None,
            }
        ]
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = rows
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("db.analysis.db_connection", lambda: mock_conn)

        from db.analysis import fetch_analysis_rows
        result = fetch_analysis_rows(datetime(2026, 6, 5), datetime(2026, 6, 12))
        assert isinstance(result, list)
        assert result[0]["category"] == "결제"

    def test_empty_result_returns_empty_list(self, monkeypatch):
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("db.analysis.db_connection", lambda: mock_conn)

        from db.analysis import fetch_analysis_rows
        result = fetch_analysis_rows(datetime(2026, 6, 5), datetime(2026, 6, 12))
        assert result == []

    def test_filters_by_ticket_inquiry_created_at(self, monkeypatch):
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("db.analysis.db_connection", lambda: mock_conn)

        from db.analysis import fetch_analysis_rows

        fetch_analysis_rows(datetime(2026, 6, 5), datetime(2026, 6, 12))

        sql = mock_cur.execute.call_args[0][0]
        assert "t.inquiry_created_at >= %s" in sql
        assert "a.analyzed_at >= %s" not in sql


class TestBuildInsightRows:
    def test_assigns_pattern_risk_from_repeated_rows(self):
        from db.insight import build_insight_rows

        source_rows = [
            {
                "ticket_id": 101,
                "user_id": 1,
                "account_id": 10,
                "content_summary": " refund delayed ",
                "category": "payment",
                "sentiment": "negative",
                "risk_level": "MID",
                "inquiry_created_at": datetime(2026, 6, 10),
            },
            {
                "ticket_id": 102,
                "user_id": 1,
                "account_id": 10,
                "content_summary": "refund delayed",
                "category": "payment",
                "sentiment": "neutral",
                "risk_level": "LOW",
                "inquiry_created_at": datetime(2026, 6, 11),
            },
            {
                "ticket_id": 201,
                "user_id": 2,
                "account_id": 20,
                "content_summary": "login issue",
                "category": "account",
                "sentiment": "negative",
                "risk_level": "HIGH",
                "inquiry_created_at": datetime(2026, 6, 11),
            },
        ]

        result = build_insight_rows(source_rows)
        rows_by_ticket = {row["ticket_id"]: row for row in result}

        assert rows_by_ticket[101]["content_summary"] == "refund delayed"
        assert rows_by_ticket[101]["pattern_risk_level"] == "HIGH"
        assert rows_by_ticket[102]["pattern_risk_level"] == "HIGH"
        assert rows_by_ticket[201]["pattern_risk_level"] == "LOW"
        assert rows_by_ticket[201]["risk_level"] == "HIGH"

    def test_defaults_blank_fields_without_losing_known_risk(self):
        from db.insight import build_insight_rows

        result = build_insight_rows(
            [
                {
                    "ticket_id": 301,
                    "user_id": 3,
                    "account_id": None,
                    "content_summary": "  hello \n world  ",
                    "category": "",
                    "sentiment": "",
                    "risk_level": "critical",
                    "inquiry_created_at": datetime(2026, 6, 12),
                }
            ]
        )

        assert result[0]["content_summary"] == "hello world"
        assert result[0]["category"] == "general"
        assert result[0]["sentiment"] == "neutral"
        assert result[0]["risk_level"] == "CRITICAL"


class TestSyncInsightRows:
    def test_returns_zero_when_no_source_rows(self, monkeypatch):
        monkeypatch.setattr("db.insight.fetch_latest_analysis_source_rows", lambda: [])

        from db.insight import sync_insight_rows

        assert sync_insight_rows() == 0

    def test_deletes_existing_rows_and_inserts_new_rows(self, monkeypatch):
        executed: list[tuple[str, tuple | None]] = []
        inserted_rows: list[tuple] = []

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {"next_id": 41}
        mock_cur.execute.side_effect = lambda sql, params=None: executed.append((sql.strip(), params))
        mock_cur.executemany.side_effect = lambda sql, params: inserted_rows.extend(params)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            "db.insight.fetch_latest_analysis_source_rows",
            lambda: [
                {
                    "ticket_id": 11,
                    "user_id": 7,
                    "account_id": 70,
                    "content_summary": "payment delay",
                    "category": "payment",
                    "sentiment": "negative",
                    "risk_level": "MID",
                    "inquiry_created_at": datetime(2026, 6, 12),
                },
                {
                    "ticket_id": 12,
                    "user_id": 7,
                    "account_id": 70,
                    "content_summary": "payment delay",
                    "category": "payment",
                    "sentiment": "negative",
                    "risk_level": "LOW",
                    "inquiry_created_at": datetime(2026, 6, 12),
                },
            ],
        )
        monkeypatch.setattr("db.insight.db_connection", lambda: mock_conn)

        from db.insight import sync_insight_rows

        inserted = sync_insight_rows()

        assert inserted == 2
        assert any(sql.startswith("DELETE FROM insight") for sql, _ in executed)
        assert any("LOCK TABLE insight" in sql for sql, _ in executed)
        assert inserted_rows[0][0] == 41
        assert inserted_rows[1][0] == 42
        assert inserted_rows[0][2] == 11
        assert inserted_rows[1][8] == "HIGH"


# ── output/pdf.py ─────────────────────────────────────────────────────────────

class TestRenderReportPdf:
    """output.pdf.render_report_pdf: report dict를 받아 PDF 바이트를 반환한다.

    xhtml2pdf(pisa)를 monkeypatch로 대체해 실제 렌더링 없이 호출 경로를 검증한다.
    """

    _MINIMAL_REPORT = {
        "title": "테스트 리포트",
        "generated_at": "2026-06-12T09:00:00",
        "window": {
            "window_start": "2026-06-05T00:00:00",
            "window_end": "2026-06-12T00:00:00",
            "days": 7,
        },
        "previous_window": {
            "window_start": "2026-05-29T00:00:00",
            "window_end": "2026-06-05T00:00:00",
            "days": 7,
        },
        "summary": {"analysis_count": 0},
        "comparisons": {
            "analysis_count": {"current": 0, "previous": 0, "change": 0, "change_rate": "데이터 없음"},
        },
        "category_counts_current": [],
        "category_counts_previous": [],
        "category_comparisons": [],
        "spike_alerts": {"hourly": [], "daily": [], "monthly": []},
        "top_requests": [],
        "ai_interpretation": {"headline": "테스트", "actions": []},
        "category_distribution": [],
        "responder_distribution": [],
        "risk_distribution": [],
        "sentiment_distribution": [],
        "routing_distribution": [],
        "analysis_rows": [],
        "review_rows": [],
        "narrative_insights": [],
        "column_insights": [],
        "report_sections": [],
    }

    def test_returns_bytes_on_success(self, monkeypatch):
        fake_pdf = b"%PDF-fake"

        mock_result = MagicMock()
        mock_result.err = 0

        def fake_create_pdf(*, dest, **_):
            dest.write(fake_pdf)
            return mock_result

        monkeypatch.setattr("output.pdf.pisa.CreatePDF", fake_create_pdf)

        from output.pdf import render_report_pdf
        result = render_report_pdf(self._MINIMAL_REPORT)
        assert isinstance(result, bytes)
        assert result == fake_pdf

    def test_raises_on_pisa_error(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.err = 1  # 오류 코드

        def fake_create_pdf(**_):
            return mock_result

        monkeypatch.setattr("output.pdf.pisa.CreatePDF", fake_create_pdf)

        from output.pdf import render_report_pdf
        with pytest.raises(RuntimeError, match="PDF 렌더링에 실패"):
            render_report_pdf(self._MINIMAL_REPORT)

    def test_category_blocks_use_actual_category_keys_for_previous_comparison(self):
        report = {
            **self._MINIMAL_REPORT,
            "category_comparisons": [
                {"category": "payment", "current": 7, "previous": 3, "change_rate": "+133.3%"},
                {"category": "bug", "current": 10, "previous": 4, "change_rate": "+150.0%"},
            ],
        }

        from output.pdf import _build_category_blocks

        html = _build_category_blocks(report)
        assert "결제" in html
        assert "인게임버그" in html
        assert "전주 대비 증가하였습니다" in html
        assert "전주 비교 데이터 없음" not in html

    def test_category_blocks_mark_new_categories_as_new(self):
        report = {
            **self._MINIMAL_REPORT,
            "category_comparisons": [
                {"category": "policy", "current": 8, "previous": 0, "change_rate": "+8"},
            ],
        }

        from output.pdf import _build_category_blocks

        html = _build_category_blocks(report)
        assert "정책" in html
        assert "NEW" in html
        assert "전주 대비 신규 발생" in html

    def test_spike_section_renders_hourly_comparison_line_chart(self, monkeypatch):
        monkeypatch.setattr("output.pdf._make_line_chart_png", lambda *args, **kwargs: "data:image/png;base64,test")
        report = {
            **self._MINIMAL_REPORT,
            "spike_alerts": {
                "hourly": [],
                "daily": [],
                "monthly": [],
                "hourly_volume": {
                    "labels": [f"{hour:02d}" for hour in range(24)],
                    "current": [hour for hour in range(24)],
                    "baseline": [hour / 2 for hour in range(24)],
                    "baseline_label": "최근 4주 평균",
                },
            },
        }

        from output.pdf import _build_spike_section

        html = _build_spike_section(report["spike_alerts"])
        assert "시간별 문의량 추이" in html
        assert "실선: 이번 주 / 점선: 최근 4주 평균" in html
        assert "data:image/png;base64,test" in html

    def test_top5_section_translates_category_labels_to_korean(self):
        report = {
            **self._MINIMAL_REPORT,
            "top_requests": [
                {
                    "rank": 1,
                    "category": "policy",
                    "topic_keywords": ["ban", "appeal"],
                    "count": 12,
                    "improvement_type": "설계 결함",
                },
                {
                    "rank": 2,
                    "category": "bug",
                    "topic_keywords": ["disconnect"],
                    "count": 8,
                    "improvement_type": "편의 개선",
                },
            ],
        }

        from output.pdf import _build_top5_section

        html = _build_top5_section(report["top_requests"])
        assert "정책" in html
        assert "인게임버그" in html
        assert ">policy<" not in html
        assert ">bug<" not in html


# ── report.py (전체 파이프라인) ───────────────────────────────────────────────

class TestReportRun:
    """report.run: 전체 파이프라인을 실행하고 결과 dict를 반환한다.

    DB·PDF·Slack·LLM 모두 monkeypatch로 차단해 통합 흐름만 검증한다.
    """

    def _patch_all(self, monkeypatch):
        empty_metrics = {
            "response_rate": 0.0, "analysis_coverage_rate": 0.0,
            "draft_coverage_rate": 0.0, "draft_ticket_rate": 0.0,
            "final_response_ticket_rate": 0.0, "draft_count": 0,
            "safety_check_count": 0, "total_tickets": 0, "category_counts": [],
        }
        monkeypatch.setattr("report.resolve_report_reference_now", lambda current: current)
        monkeypatch.setattr("report.metrics_query.fetch", lambda *_: empty_metrics)
        monkeypatch.setattr("report.fetch_analysis_rows", lambda *_: [])
        monkeypatch.setattr("report.top_requests_query.fetch", lambda *_: [])
        monkeypatch.setattr("report.spike_alerts_query.detect", lambda *_: {"hourly": [], "daily": [], "monthly": []})
        monkeypatch.setattr("report.generate_ai_actions", lambda *_: {"headline": "테스트", "actions": []})

    def test_run_returns_required_keys(self, monkeypatch):
        self._patch_all(monkeypatch)
        import report as r
        result = r.run(days=7)
        assert "report" in result
        assert "pdf_bytes" in result
        assert "slack_result" in result

    def test_pdf_bytes_none_when_render_false(self, monkeypatch):
        self._patch_all(monkeypatch)
        import report as r
        result = r.run(days=7, render_pdf=False)
        assert result["pdf_bytes"] is None

    def test_pdf_bytes_present_when_render_true(self, monkeypatch):
        self._patch_all(monkeypatch)
        monkeypatch.setattr("report.render_report_pdf", lambda *_: b"%PDF-fake")
        import report as r
        result = r.run(days=7, render_pdf=True)
        assert result["pdf_bytes"] == b"%PDF-fake"

    def test_slack_not_sent_when_flag_false(self, monkeypatch):
        self._patch_all(monkeypatch)
        import report as r
        result = r.run(days=7, send_to_slack=False)
        assert result["slack_result"] is None

    def test_send_to_slack_requires_channel(self, monkeypatch):
        self._patch_all(monkeypatch)
        import report as r
        with pytest.raises(ValueError, match="slack_channel"):
            r.run(days=7, send_to_slack=True, slack_channel=None)

    def test_category_comparisons_in_payload(self, monkeypatch):
        """build_report_payload가 category_comparisons 키를 포함하는지 확인한다."""
        self._patch_all(monkeypatch)
        import report as r
        result = r.run(days=7)
        assert "category_comparisons" in result["report"]

    def test_run_records_operational_scores(self, monkeypatch):
        self._patch_all(monkeypatch)
        captured: dict[str, object] = {}
        monkeypatch.setattr("report.record_current_scores", lambda scores, **kwargs: captured.update({"scores": scores, "kwargs": kwargs}))

        import report as r

        result = r.run(days=7, render_pdf=False, send_to_slack=False)

        assert result["report"] is not None
        assert captured["scores"]["report_generated"] is True
        assert captured["scores"]["pdf_rendered"] is False
        assert captured["scores"]["slack_delivered"] is False
        assert captured["scores"]["ai_fallback_used"] is False

    def test_run_uses_resolved_reference_now(self, monkeypatch):
        self._patch_all(monkeypatch)
        resolved_now = datetime(2020, 9, 29, 18, 57)
        captured: dict[str, object] = {}

        monkeypatch.setattr("report.resolve_report_reference_now", lambda current: resolved_now)
        monkeypatch.setattr(
            "report.metrics_query.fetch",
            lambda window: captured.setdefault("metric_windows", []).append(window) or {
                "response_rate": 0.0,
                "analysis_coverage_rate": 0.0,
                "draft_coverage_rate": 0.0,
                "draft_ticket_rate": 0.0,
                "final_response_ticket_rate": 0.0,
                "draft_count": 0,
                "safety_check_count": 0,
                "total_tickets": 0,
                "category_counts": [],
            },
        )
        monkeypatch.setattr(
            "report.fetch_analysis_rows",
            lambda start, end: captured.setdefault("analysis_windows", []).append((start, end)) or [],
        )

        import report as r

        r.run(days=7)

        assert captured["metric_windows"][0]["window_end"] == resolved_now
        assert captured["analysis_windows"][0][1] == resolved_now


def test_weekly_report_dag_materializes_insight_before_report(monkeypatch):
    dependencies: list[tuple[str, str]] = []

    class _FakeTaskInvocation:
        def __init__(self, task_id: str):
            self.task_id = task_id

        def __rshift__(self, other):
            dependencies.append((self.task_id, other.task_id))
            return other

    def fake_task(*, task_id: str):
        def decorator(fn):
            def wrapper(*args, **kwargs):
                return _FakeTaskInvocation(task_id)

            return wrapper

        return decorator

    def fake_dag(**_kwargs):
        def decorator(fn):
            def wrapper(*args, **kwargs):
                return fn(*args, **kwargs)

            return wrapper

        return decorator

    airflow_module = types.ModuleType("airflow")
    decorators_module = types.ModuleType("airflow.decorators")
    decorators_module.dag = fake_dag
    decorators_module.task = fake_task
    pendulum_module = types.ModuleType("pendulum")
    pendulum_module.timezone = lambda name: name
    pendulum_module.datetime = lambda *args, **kwargs: datetime(*args[:3])

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.decorators", decorators_module)
    monkeypatch.setitem(sys.modules, "pendulum", pendulum_module)

    module_path = Path(__file__).resolve().parents[3] / "apps" / "weekly_report" / "airflow" / "weekly_report_dag.py"
    spec = importlib.util.spec_from_file_location("weekly_report_dag_under_test", module_path)
    module = importlib.util.module_from_spec(spec)

    assert spec is not None
    assert spec.loader is not None

    spec.loader.exec_module(module)

    assert ("materialize_insight_rows", "run_weekly_report") in dependencies
