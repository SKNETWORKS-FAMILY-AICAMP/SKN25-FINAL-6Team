from __future__ import annotations

from types import SimpleNamespace

from src.dashboard.workflow.weekly_report import pdf


def _sample_report() -> dict[str, object]:
    return {
        "title": "운영 주간 보고서 - 2026-05-27",
        "generated_at": "2026-05-27T10:00:00",
        "window": {"window_start": "2026-05-20", "window_end": "2026-05-27"},
        "previous_window": {"window_start": "2026-05-13", "window_end": "2026-05-20"},
        "summary": {
            "analysis_count": 12,
            "high_risk_count": 3,
            "negative_sentiment_count": 4,
            "human_review_count": 5,
            "response_rate": 0.75,
            "analysis_coverage_rate": 0.9,
            "draft_coverage_rate": 0.8,
            "final_response_ticket_rate": 0.7,
            "high_risk_rate": 0.25,
            "negative_sentiment_rate": 0.33,
            "human_review_rate": 0.41,
            "urgent_alert_rate": 0.12,
        },
        "comparisons": {
            "analysis_count": {"change_rate": "+20%"},
            "high_risk_count": {"change_rate": "-10%"},
            "negative_sentiment_count": {"change_rate": "+5%"},
            "human_review_count": {"change_rate": "+0%"},
        },
        "ai_interpretation": {
            "headline": "주간 해석",
            "summary": "전체 흐름은 안정적입니다.",
            "bullets": ["bullet 1", "bullet 2", "bullet 3", "bullet 4"],
            "actions": ["action 1", "action 2", "action 3"],
        },
        "category_distribution": [{"label": "payment", "value": 5}],
        "risk_distribution": [{"label": "high", "value": 3}],
        "responder_distribution": [{"label": "rag_reply", "value": 7}],
        "sentiment_distribution": [{"label": "negative", "value": 4}],
        "routing_distribution": [{"label": "human_review", "value": 5}],
        "review_rows": [
            {
                "ticket_id": f"ticket-{index}",
                "title": f"title-{index}",
                "risk_level": "high",
                "category": "payment",
                "sentiment": "negative",
                "routing_target": "human_review",
                "ai_row_interpretation": f"review-{index}",
            }
            for index in range(7)
        ],
        "analysis_rows": [
            {
                "analysis_id": f"analysis-{index}",
                "ticket_id": f"ticket-{index}",
                "title": f"title-{index}",
                "category": "payment",
                "risk_level": "high",
                "routing_target": "human_review",
            }
            for index in range(10)
        ],
    }


def test_build_html_includes_chart_gallery_and_preview_limits(monkeypatch) -> None:
    monkeypatch.setattr(pdf, "_build_plotly_chart_data_uri", lambda title, rows, kind: "data:image/png;base64,TEST")

    html = pdf._build_html(_sample_report())

    assert "주간 분포 차트" in html
    assert html.count("data:image/png;base64,TEST") == 6
    assert "review-4" in html
    assert "review-5" not in html
    assert "analysis-7" in html
    assert "analysis-8" not in html
    assert "분석 원본 미리보기" in html


def test_render_report_pdf_uses_pisa_and_returns_bytes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_create_pdf(*, src, dest, encoding):
        captured["src"] = src
        captured["encoding"] = encoding
        dest.write(b"%PDF-FAKE")
        return SimpleNamespace(err=False)

    monkeypatch.setattr(pdf, "_build_plotly_chart_data_uri", lambda title, rows, kind: None)
    monkeypatch.setattr(pdf.pisa, "CreatePDF", _fake_create_pdf)

    result = pdf.render_report_pdf(_sample_report())

    assert result == b"%PDF-FAKE"
    assert captured["encoding"] == "utf-8"
    assert "차트를 생성하지 못했습니다." in str(captured["src"])
