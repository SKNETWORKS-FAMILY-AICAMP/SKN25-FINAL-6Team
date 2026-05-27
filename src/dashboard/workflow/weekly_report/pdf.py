"""HTML/CSS-based PDF rendering helpers for the weekly dashboard report."""

from __future__ import annotations

import io
from html import escape
from typing import Any

from xhtml2pdf import pisa


def _text(value: object, fallback: str = "-") -> str:
    raw = str(value or "").strip()
    return raw if raw else fallback


def _percent(value: object) -> str:
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "-"


def _number(value: object) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "-"


def _change_text(value: object) -> str:
    text = _text(value)
    if text == "-":
        return "이전 주 비교 정보 없음"
    if text in {"0", "0.0%", "+0", "+0.0%", "-0.0%"}:
        return "이전 주와 비슷함"
    return f"이전 주 대비 {text}"


def _build_metric_cards(summary: dict[str, Any], comparisons: dict[str, Any]) -> str:
    cards = [
        ("분석 건수", _number(summary.get("analysis_count")), _change_text(comparisons.get("analysis_count", {}).get("change_rate"))),
        ("고위험 문의", _number(summary.get("high_risk_count")), _change_text(comparisons.get("high_risk_count", {}).get("change_rate"))),
        ("부정 반응 문의", _number(summary.get("negative_sentiment_count")), _change_text(comparisons.get("negative_sentiment_count", {}).get("change_rate"))),
        ("사람 검토 필요 문의", _number(summary.get("human_review_count")), _change_text(comparisons.get("human_review_count", {}).get("change_rate"))),
    ]
    return "".join(
        f"""
        <td class="metric-card">
            <div class="metric-label">{escape(label)}</div>
            <div class="metric-value">{escape(value)}</div>
            <div class="metric-delta">{escape(delta)}</div>
        </td>
        """
        for label, value, delta in cards
    )


def _build_summary_table(summary: dict[str, Any]) -> str:
    rows = [
        ("응답 완료 비율", _percent(summary.get("response_rate"))),
        ("분석 완료 비율", _percent(summary.get("analysis_coverage_rate"))),
        ("초안 작성 비율", _percent(summary.get("draft_coverage_rate"))),
        ("최종 응답 완료 비율", _percent(summary.get("final_response_ticket_rate"))),
        ("고위험 문의 비율", _percent(summary.get("high_risk_rate"))),
        ("부정 반응 문의 비율", _percent(summary.get("negative_sentiment_rate"))),
        ("사람 검토 필요 비율", _percent(summary.get("human_review_rate"))),
        ("즉시 알림 필요 비율", _percent(summary.get("urgent_alert_rate"))),
    ]
    return "".join(
        f"""
        <tr>
            <td class="summary-label">{escape(label)}</td>
            <td class="summary-value">{escape(value)}</td>
        </tr>
        """
        for label, value in rows
    )


def _build_bullet_list(items: list[str]) -> str:
    if not items:
        return "<li>자동 해석 결과가 아직 없습니다.</li>"
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def _build_actions(actions: list[str]) -> str:
    if not actions:
        return "<p class='muted'>이번 주에 바로 조치할 권고 사항은 없습니다.</p>"
    return "".join(
        f"""
        <div class="action-item">
            <span class="action-index">{index}</span>
            <span class="action-text">{escape(item)}</span>
        </div>
        """
        for index, item in enumerate(actions, start=1)
    )


def _build_review_cards(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p class='muted'>우선 확인이 필요한 문의가 없습니다.</p>"

    cards: list[str] = []
    for row in rows[:8]:
        cards.append(
            f"""
            <div class="review-card">
                <table class="review-head-table">
                    <tr>
                        <td class="review-ticket">문의 #{escape(_text(row.get('ticket_id')))}</td>
                        <td class="review-risk">{escape(_text(row.get('risk_level')))}</td>
                    </tr>
                </table>
                <div class="review-title">{escape(_text(row.get('title')))}</div>
                <div class="review-meta">
                    분류: {escape(_text(row.get('category')))} |
                    반응: {escape(_text(row.get('sentiment')))} |
                    다음 처리: {escape(_text(row.get('routing_target')))}
                </div>
                <div class="review-body">{escape(_text(row.get('ai_row_interpretation')))}</div>
            </div>
            """
        )
    return "".join(cards)


def _build_analysis_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<tr><td colspan='6' class='muted'>표시할 분석 원본이 없습니다.</td></tr>"

    return "".join(
        f"""
        <tr>
            <td>{escape(_text(row.get('analysis_id')))}</td>
            <td>{escape(_text(row.get('ticket_id')))}</td>
            <td>{escape(_text(row.get('title')))}</td>
            <td>{escape(_text(row.get('category')))}</td>
            <td>{escape(_text(row.get('risk_level')))}</td>
            <td>{escape(_text(row.get('routing_target')))}</td>
        </tr>
        """
        for row in rows[:12]
    )


def _build_html(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    comparisons = report.get("comparisons", {})
    interpretation = report.get("ai_interpretation", {}) or {}
    window = report.get("window", {})
    previous_window = report.get("previous_window", {})
    title = _text(report.get("title"), "운영 주간 보고서")
    generated_at = _text(report.get("generated_at"))

    return f"""
    <html>
    <head>
        <meta charset="utf-8" />
        <style>
            @page {{
                size: A4;
                margin: 18mm 14mm 16mm 14mm;
            }}
            body {{
                font-family: HYGothic-Medium;
                color: #172033;
                font-size: 10.5pt;
                line-height: 1.5;
                background: #f4f7fb;
            }}
            .hero {{
                background: #0f172a;
                color: white;
                padding: 22px 24px;
                border-radius: 14px;
                margin-bottom: 16px;
            }}
            .eyebrow {{
                font-size: 8.5pt;
                color: #cbd5e1;
                margin-bottom: 8px;
                letter-spacing: 1px;
            }}
            .title {{
                font-size: 23pt;
                font-weight: bold;
                margin-bottom: 8px;
            }}
            .subtitle {{
                font-size: 9.5pt;
                color: #e2e8f0;
                line-height: 1.6;
            }}
            .section {{
                margin-top: 14px;
                padding: 16px 18px;
                border: 1px solid #d9e2ef;
                border-radius: 12px;
                background: #ffffff;
            }}
            .section-title {{
                font-size: 14pt;
                font-weight: bold;
                color: #0f172a;
                margin-bottom: 12px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            .metric-card {{
                width: 25%;
                padding: 12px 14px;
                border: 1px solid #dbe3ef;
                background: #f8fafc;
                vertical-align: top;
            }}
            .metric-label {{
                font-size: 9pt;
                color: #64748b;
                margin-bottom: 8px;
            }}
            .metric-value {{
                font-size: 18pt;
                font-weight: bold;
                color: #0f172a;
                margin-bottom: 5px;
            }}
            .metric-delta {{
                font-size: 8.5pt;
                color: #334155;
            }}
            .summary-label, .summary-value {{
                border-bottom: 1px solid #e5e7eb;
                padding: 8px 10px;
            }}
            .summary-label {{
                width: 68%;
                color: #475569;
            }}
            .summary-value {{
                width: 32%;
                font-weight: bold;
                text-align: right;
                color: #0f172a;
            }}
            .interpretation-box {{
                padding: 14px 16px;
                border-left: 5px solid #0f766e;
                background: #effcf8;
                margin-bottom: 12px;
            }}
            .interpretation-headline {{
                font-size: 13pt;
                font-weight: bold;
                margin-bottom: 8px;
                color: #0f172a;
            }}
            .muted {{
                color: #64748b;
            }}
            ul {{
                margin: 8px 0 0 18px;
                padding: 0;
            }}
            li {{
                margin-bottom: 6px;
            }}
            .column-title {{
                font-size: 11pt;
                font-weight: bold;
                color: #0f172a;
                margin-bottom: 8px;
            }}
            .action-item {{
                margin-bottom: 8px;
                padding: 9px 11px;
                border: 1px solid #f1dcc7;
                border-radius: 10px;
                background: #fff7ed;
            }}
            .action-index {{
                display: inline-block;
                width: 18px;
                height: 18px;
                line-height: 18px;
                text-align: center;
                background: #f97316;
                color: white;
                border-radius: 50%;
                font-size: 8.5pt;
                margin-right: 8px;
            }}
            .review-card {{
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 12px 14px;
                margin-bottom: 10px;
                background: #fcfcfd;
            }}
            .review-head-table {{
                margin-bottom: 6px;
            }}
            .review-ticket {{
                font-weight: bold;
                color: #0f172a;
            }}
            .review-risk {{
                text-align: right;
                color: #b91c1c;
                font-size: 9pt;
                font-weight: bold;
            }}
            .review-title {{
                font-size: 11.5pt;
                font-weight: bold;
                margin-bottom: 6px;
            }}
            .review-meta {{
                font-size: 9pt;
                color: #64748b;
                margin-bottom: 8px;
            }}
            .review-body {{
                font-size: 10pt;
                color: #1f2937;
            }}
            .analysis-table th {{
                background: #f1f5f9;
                color: #0f172a;
                font-size: 9pt;
                padding: 8px;
                border: 1px solid #dbe3ef;
                text-align: left;
            }}
            .analysis-table td {{
                padding: 8px;
                border: 1px solid #e5e7eb;
                font-size: 9pt;
                vertical-align: top;
            }}
        </style>
    </head>
    <body>
        <div class="hero">
            <div class="eyebrow">WEEKLY OPERATIONS REPORT</div>
            <div class="title">{escape(title)}</div>
            <div class="subtitle">
                생성 시각 {escape(generated_at)}<br/>
                이번 기간 {escape(_text(window.get("window_start")))} ~ {escape(_text(window.get("window_end")))}<br/>
                비교 기간 {escape(_text(previous_window.get("window_start")))} ~ {escape(_text(previous_window.get("window_end")))}
            </div>
        </div>

        <div class="section">
            <div class="section-title">주간 지표 요약</div>
            <table>
                <tr>{_build_metric_cards(summary, comparisons)}</tr>
            </table>
        </div>

        <div class="section">
            <div class="section-title">AI 종합 해석</div>
            <div class="interpretation-box">
                <div class="interpretation-headline">{escape(_text(interpretation.get("headline"), "이번 주 운영 해석"))}</div>
                <div>{escape(_text(interpretation.get("summary"), "자동 해석 결과가 아직 없습니다."))}</div>
            </div>
            <table>
                <tr>
                    <td width="52%" style="vertical-align: top; padding-right: 8px;">
                        <div class="column-title">AI가 짚은 핵심 내용</div>
                        <ul>{_build_bullet_list(interpretation.get("bullets", []))}</ul>
                    </td>
                    <td width="48%" style="vertical-align: top; padding-left: 8px;">
                        <div class="column-title">바로 볼 액션</div>
                        {_build_actions(interpretation.get("actions", []))}
                    </td>
                </tr>
            </table>
        </div>

        <div class="section">
            <div class="section-title">주요 비율과 진행 현황</div>
            <table>{_build_summary_table(summary)}</table>
        </div>

        <div class="section">
            <div class="section-title">우선 확인이 필요한 문의</div>
            {_build_review_cards(report.get("review_rows", []))}
        </div>

        <div class="section">
            <div class="section-title">분석 원본 요약 샘플</div>
            <table class="analysis-table">
                <tr>
                    <th>분석 번호</th>
                    <th>문의 번호</th>
                    <th>문의 제목</th>
                    <th>문의 분류</th>
                    <th>위험도</th>
                    <th>다음 처리</th>
                </tr>
                {_build_analysis_table(report.get("analysis_rows", []))}
            </table>
        </div>
    </body>
    </html>
    """


def render_report_pdf(report: dict[str, Any]) -> bytes:
    """Render the weekly report payload into a styled PDF byte stream."""

    html = _build_html(report)
    buffer = io.BytesIO()
    pdf = pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")
    if pdf.err:
        raise RuntimeError("weekly report PDF rendering failed")
    return buffer.getvalue()
