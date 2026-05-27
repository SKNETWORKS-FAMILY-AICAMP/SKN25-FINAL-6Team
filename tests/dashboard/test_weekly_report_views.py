from __future__ import annotations

from typing import Any

from src.dashboard.util import views


class _DummyContext:
    def __init__(self, target: "_DummyStreamlit") -> None:
        self._target = target

    def __enter__(self) -> "_DummyContext":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _DummyColumn(_DummyContext):
    def metric(self, label: str, value: Any, delta: Any = None) -> None:
        self._target.metric_calls.append((label, value, delta))


class _DummyStreamlit:
    def __init__(self) -> None:
        self.metric_calls: list[tuple[str, Any, Any]] = []
        self.caption_calls: list[str] = []
        self.markdown_calls: list[str] = []
        self.write_calls: list[str] = []
        self.expander_calls: list[tuple[str, bool]] = []
        self.subheader_calls: list[str] = []

    def columns(self, spec: Any, gap: str | None = None) -> list[_DummyColumn]:
        count = spec if isinstance(spec, int) else len(spec)
        return [_DummyColumn(self) for _ in range(count)]

    def container(self, border: bool = False) -> _DummyContext:
        return _DummyContext(self)

    def expander(self, label: str, expanded: bool = False) -> _DummyContext:
        self.expander_calls.append((label, expanded))
        return _DummyContext(self)

    def caption(self, text: str) -> None:
        self.caption_calls.append(text)

    def markdown(self, text: str) -> None:
        self.markdown_calls.append(text)

    def write(self, text: str) -> None:
        self.write_calls.append(str(text))

    def subheader(self, text: str) -> None:
        self.subheader_calls.append(text)

    def download_button(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_render_weekly_report_section_compact_limits_rows(monkeypatch) -> None:
    dummy_st = _DummyStreamlit()
    priority_calls: list[list[dict[str, Any]]] = []
    table_calls: list[tuple[list[dict[str, Any]], str]] = []
    chart_calls: list[str] = []

    monkeypatch.setattr(views, "st", dummy_st)
    monkeypatch.setattr(views, "render_ai_interpretation", lambda report: None)
    monkeypatch.setattr(views, "_render_window_caption", lambda window, prefix: None)
    monkeypatch.setattr(
        views,
        "_render_priority_table",
        lambda rows, *, title, columns, kind: priority_calls.append(rows),
    )
    monkeypatch.setattr(
        views,
        "render_data_table",
        lambda rows, *, kind="default": table_calls.append((rows, kind)),
    )
    monkeypatch.setattr(views, "render_chart_box", lambda title, data, **kwargs: chart_calls.append(title))

    report = {
        "window": {"days": 7, "window_start": "2026-05-20", "window_end": "2026-05-27"},
        "summary": {
            "analysis_count": 12,
            "high_risk_count": 3,
            "negative_sentiment_count": 4,
            "human_review_count": 6,
            "response_rate": 0.75,
            "analysis_coverage_rate": 0.9,
            "draft_coverage_rate": 0.8,
            "final_response_ticket_rate": 0.7,
        },
        "comparisons": {
            "analysis_count": {"change_rate": "+20%"},
            "high_risk_count": {"change_rate": "-10%"},
            "negative_sentiment_count": {"change_rate": "+5%"},
            "human_review_count": {"change_rate": "+0%"},
        },
        "review_rows": [{"analysis_id": index, "ticket_id": index} for index in range(7)],
        "analysis_rows": [{"analysis_id": index, "ticket_id": index} for index in range(10)],
        "narrative_insights": ["insight 1", "insight 2", "insight 3", "insight 4"],
        "ai_interpretation": {"actions": ["action 1", "action 2", "action 3"]},
        "category_distribution": [],
        "risk_distribution": [],
        "responder_distribution": [],
        "sentiment_distribution": [],
        "routing_distribution": [],
    }

    views.render_weekly_report_section(
        report,
        compact=True,
        review_limit=5,
        analysis_preview_limit=8,
    )

    assert len(dummy_st.metric_calls) == 4
    assert len(priority_calls) == 1
    assert len(priority_calls[0]) == 5
    assert len(table_calls) == 2
    assert len(table_calls[0][0]) == 8
    assert table_calls[0][1] == "analysis"
    assert len(table_calls[1][0]) == 10
    assert chart_calls == [
        "문의 분류",
        "위험도 분포",
        "응답 주체 분포",
        "이용자 반응 분포",
        "다음 처리 분포",
        "처리 단계 비율",
    ]
    assert ("분포 차트 보기", False) in dummy_st.expander_calls
    assert ("분석 원본 전체 보기", False) in dummy_st.expander_calls
    assert any("상위 5건" in text for text in dummy_st.caption_calls)
    assert any("상위 8건" in text for text in dummy_st.caption_calls)
