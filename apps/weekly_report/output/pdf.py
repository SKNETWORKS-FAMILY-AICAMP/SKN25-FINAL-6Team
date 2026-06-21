"""HTML/CSS 기반 주간 리포트 PDF 렌더링."""

from __future__ import annotations

import base64
import io
import os
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Any

from xhtml2pdf import pisa

from common.observability.langfuse import observe_if_enabled
from observability.langfuse import link_weekly_report_trace


FONT_FAMILY_NAME = "DashboardKorean"
FONT_REGULAR_ENV = "DASHBOARD_WEEKLY_REPORT_FONT_REGULAR"
FONT_BOLD_ENV = "DASHBOARD_WEEKLY_REPORT_FONT_BOLD"

_CATEGORIES = ["결제", "지급", "뽑기", "계정", "인게임버그"]


# ── 폰트 유틸리티 ──────────────────────────────────────────────────────────────

def _existing_font_path(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value).expanduser()
    return candidate if candidate.exists() else None


def _resolve_pdf_fonts() -> dict[str, Path] | None:
    candidate_pairs = [
        (os.environ.get(FONT_REGULAR_ENV), os.environ.get(FONT_BOLD_ENV)),
        (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"),
        (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunsl.ttf"),
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf"),
        ("/usr/share/fonts/truetype/nanum/NanumSquareR.ttf",
         "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
         "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ]
    for reg, bold in candidate_pairs:
        reg_path = _existing_font_path(reg)
        if reg_path is None:
            continue
        return {"regular": reg_path, "bold": _existing_font_path(bold) or reg_path}
    return None


def _font_face_css() -> str:
    fonts = _resolve_pdf_fonts()
    if fonts is None:
        return ""
    return f"""
        @font-face {{
            font-family: '{FONT_FAMILY_NAME}';
            src: url('{fonts["regular"].resolve().as_uri()}');
            font-weight: normal;
        }}
        @font-face {{
            font-family: '{FONT_FAMILY_NAME}';
            src: url('{fonts["bold"].resolve().as_uri()}');
            font-weight: bold;
        }}
    """


def _resolve_resource_path(uri: str, rel: str | None = None) -> str:
    del rel
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        path = unquote(parsed.path or "")
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path.lstrip("/")
        return path
    if parsed.scheme == "":
        candidate = Path(uri)
        if candidate.exists():
            return str(candidate.resolve())
    return uri


# ── 공통 포매터 ────────────────────────────────────────────────────────────────

def _text(value: object, fallback: str = "-") -> str:
    raw = str(value or "").strip()
    return raw if raw else fallback


# ── 차트 렌더링 ────────────────────────────────────────────────────────────────

def _make_bar_chart_png(
    labels: list[str],
    values: list[float],
    colors: list[str],
    *,
    width: int = 720,
    height: int = 300,
) -> str | None:
    """Plotly 바차트 PNG → data URI. 실패하면 None."""
    if not labels:
        return None
    try:
        import plotly.graph_objects as go
        import plotly.io as pio

        fig = go.Figure(data=[go.Bar(
            x=labels,
            y=values,
            marker={"color": colors},
            text=[f"{int(v):,}" for v in values],
            textposition="outside",
        )])
        fig.update_layout(
            paper_bgcolor="#ffffff",
            plot_bgcolor="#f8f9fb",
            margin={"l": 28, "r": 16, "t": 16, "b": 36},
            font={"family": "Arial", "size": 11, "color": "#1a1a2e"},
            showlegend=False,
            yaxis={"gridcolor": "#f3f4f6", "zeroline": False},
            xaxis={"tickfont": {"size": 10}},
        )
        image_bytes = pio.to_image(fig, format="png", width=width, height=height, scale=2)
        return "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    except Exception:
        return None


# ── 섹션 빌더 ──────────────────────────────────────────────────────────────────

def _summary_bullets(report: dict[str, Any]) -> list[str]:
    """AI 요약 왼쪽 컬럼 — 주간 지표 요약 bullet 자동 생성."""
    bullets: list[str] = []

    summary = report.get("summary") or {}
    total = int(summary.get("analysis_count") or 0)
    comp = (report.get("comparisons") or {}).get("analysis_count") or {}
    change_rate = _text(comp.get("change_rate"), "-")
    bullets.append(f"총 응대 건수 {total:,}건 — 전주 대비 {change_rate}")

    cur_map = {r.get("category", ""): int(r.get("count", 0))
               for r in (report.get("category_counts_current") or [])}
    prev_map = {r.get("category", ""): int(r.get("count", 0))
                for r in (report.get("category_counts_previous") or [])}

    notable: list[tuple[float, str]] = []
    for cat in _CATEGORIES:
        cur = cur_map.get(cat, 0)
        prev = prev_map.get(cat, 0)
        if prev > 0:
            pct = (cur - prev) / prev * 100
            if abs(pct) >= 10:
                word = "증가" if pct > 0 else "감소"
                notable.append((abs(pct), f"{cat} 카테고리 전주 대비 {abs(pct):.0f}% {word}"))
    for _, txt in sorted(notable, reverse=True)[:2]:
        bullets.append(txt)

    spike = report.get("spike_alerts") or {}
    anomaly = [d for d in (spike.get("daily") or []) if d.get("level") != "normal"]
    if anomaly:
        w = max(anomaly, key=lambda x: x.get("pct_change", 0))
        bullets.append(f"{w.get('day', '?')} {w.get('pct_change', 0)*100:+.0f}% 폭증 감지")

    critical_h = [h for h in (spike.get("hourly") or []) if h.get("level") == "critical"]
    if critical_h:
        times = ", ".join(f"{h['hour']:02d}시" for h in critical_h[:3])
        bullets.append(f"집중 위험 시간대: {times}")

    return bullets[:5] if bullets else ["이번 주 특이 사항 없음"]


def _build_ai_section(report: dict[str, Any]) -> str:
    """AI 요약 카드 — 주간지표요약(좌) · 권장액션(우) 2컬럼."""
    ai = report.get("ai_interpretation") or {}
    actions = ai.get("actions") or []

    def li(text: str) -> str:
        return f"<li>{escape(text)}</li>"

    # 왼쪽: 주간 지표 요약
    left_items = "".join(li(b) for b in _summary_bullets(report))

    # 오른쪽: AI 권장 액션
    if actions:
        right_items = "".join(
            li(f"[{a.get('category','')}] {a.get('action','')} — {a.get('reason','')}")
            for a in actions[:5]
        )
    else:
        right_items = "<li>이번 주 권장 액션이 없습니다</li>"

    return f"""
    <div class="ai-badge">AI SUMMARY</div>
    <table class="ai-cols-table">
        <tr>
            <td class="ai-col">
                <div class="ai-col-title">주간 지표 요약</div>
                <ul class="ai-list">{left_items}</ul>
            </td>
            <td class="ai-col">
                <div class="ai-col-title">권장 액션</div>
                <ul class="ai-list">{right_items}</ul>
            </td>
        </tr>
    </table>
    """


def _build_category_blocks(report: dict[str, Any]) -> str:
    """카테고리별 건수 블록 — 건수 · ▲▼ badge · 증감 텍스트."""
    cur_map = {r.get("category", ""): int(r.get("count", 0))
               for r in (report.get("category_counts_current") or [])}
    prev_map = {r.get("category", ""): int(r.get("count", 0))
                for r in (report.get("category_counts_previous") or [])}

    cells: list[str] = []
    for cat in _CATEGORIES:
        cur = cur_map.get(cat, 0)
        prev = prev_map.get(cat, 0)

        if prev > 0:
            pct = (cur - prev) / prev * 100
            if pct > 5:
                badge_cls = "badge-up"
                arrow = "▲"
                note = "전주 대비 증가하였습니다"
            elif pct < -5:
                badge_cls = "badge-dn"
                arrow = "▼"
                note = "전주 대비 감소하였습니다"
            else:
                badge_cls = "badge-eq"
                arrow = "→"
                note = "전주와 동일합니다"
            badge_html = f'<div><span class="{badge_cls}">{arrow} {abs(pct):.0f}%</span></div>'
        else:
            badge_html = '<div><span class="badge-eq">— 비교 없음</span></div>'
            note = "전주 비교 데이터 없음"

        cells.append(f"""
        <td class="m-block">
            <div class="m-cat">{escape(cat)}</div>
            <div class="m-count">{cur:,}</div>
            {badge_html}
            <div class="m-note">{escape(note)}</div>
        </td>
        """)

    return f"<table class='m-row'><tr>{''.join(cells)}</tr></table>"


def _build_heatmap(hourly: list[dict[str, Any]]) -> str:
    """24시간 히트맵 — 두 줄(AM/PM) 테이블, Z-Score 기반 색상."""
    by_hour = {item["hour"]: item for item in hourly}

    def cell(h: int) -> str:
        item = by_hour.get(h, {})
        level = item.get("level", "normal")
        cnt = item.get("current", "")
        if level == "critical":
            bg, fg = "#b45309", "#ffffff"
        elif level == "warning":
            bg, fg = "#f97316", "#ffffff"
        else:
            bg, fg = "#f0f2f5", "#9ca3af"
        cnt_txt = f"<br/>{cnt}" if cnt else ""
        return (
            f'<td style="background:{bg};color:{fg};text-align:center;'
            f'padding:4px 1px;font-size:7pt;border:1px solid #e5e7eb;width:4.16%;">'
            f'{h:02d}시{cnt_txt}</td>'
        )

    am = "".join(cell(h) for h in range(12))
    pm = "".join(cell(h) for h in range(12, 24))
    legend = (
        '<div style="font-size:7pt;color:#888;margin-top:3px;">'
        '<span style="color:#b45309;font-weight:bold;">■ 위험(Z≥3)</span>&nbsp;&nbsp;'
        '<span style="color:#f97316;font-weight:bold;">■ 경고(Z≥2)</span>&nbsp;&nbsp;'
        '□ 정상</div>'
    )
    return (
        f'<div class="heat-label">시간별 문의량 (운영 인력 배치)</div>'
        f'<table style="width:100%;table-layout:fixed;border-collapse:collapse;">'
        f'<tr>{am}</tr><tr>{pm}</tr></table>'
        f'<div style="font-size:7pt;color:#bbb;margin-top:1px;">'
        f'위: 00~11시 / 아래: 12~23시</div>'
        f'{legend}'
    )


def _build_spike_section(spike_alerts: dict[str, Any]) -> str:
    """전주 폭증(좌) · 월별 추세(우) 2컬럼."""
    daily = spike_alerts.get("daily") or []
    hourly = spike_alerts.get("hourly") or []
    monthly = spike_alerts.get("monthly") or []

    # ── 좌: 7일 바차트 + 히트맵 ──
    if daily:
        labels = [r.get("day", "?") for r in daily]
        values = [float(r.get("this_week", 0)) for r in daily]
        colors = [
            "#b45309" if r.get("level") == "critical" else
            "#f97316" if r.get("level") == "warning" else
            "rgba(180,83,9,0.45)"
            for r in daily
        ]
        uri = _make_bar_chart_png(labels, values, colors, width=480, height=270)
        left_chart = (
            f'<img style="width:100%;height:auto;" src="{uri}" />'
            if uri else
            "<table class='fb-table'>" +
            "".join(f"<tr><td>{escape(r.get('day',''))}</td><td>{int(r.get('this_week',0)):,}건</td></tr>" for r in daily) +
            "</table>"
        )
        anomaly = [d for d in daily if d.get("level") != "normal"]
        sub = (
            "폭증 감지: " + ", ".join(f"{d['day']} {d['pct_change']*100:+.0f}%({d['level']})" for d in anomaly)
            if anomaly else "이번 주 일별 폭증 감지 없음 ✅"
        )
    else:
        left_chart = "<div class='no-data'>일별 문의량 데이터가 없습니다.</div>"
        sub = ""

    # ── 우: 4주 바차트 + 요약 ──
    if monthly:
        labels_m = [r.get("label", "?") for r in monthly]
        values_m = [float(r.get("count", 0)) for r in monthly]
        colors_m = [
            "rgba(180,83,9,0.85)",
            "rgba(180,83,9,0.65)",
            "rgba(180,83,9,0.45)",
            "rgba(180,83,9,0.25)",
        ][:len(values_m)]
        uri_m = _make_bar_chart_png(labels_m, values_m, colors_m, width=440, height=270)
        right_chart = (
            f'<img style="width:100%;height:auto;" src="{uri_m}" />'
            if uri_m else
            "<table class='fb-table'>" +
            "".join(f"<tr><td>{escape(r.get('label',''))}</td><td>{int(r.get('count',0)):,}건</td></tr>" for r in monthly) +
            "</table>"
        )
        # 요약 텍스트
        if len(monthly) >= 2:
            this_w, prev_w = int(monthly[0].get("count", 0)), int(monthly[1].get("count", 0))
            if prev_w > 0:
                pct = (this_w - prev_w) / prev_w * 100
                trend_txt = f"이번 주 총 <strong>{this_w:,}건</strong> (전주 대비 {pct:+.1f}%)"
            else:
                trend_txt = f"이번 주 총 <strong>{this_w:,}건</strong>"
        else:
            trend_txt = "이번 주 데이터 집계 없음"
        summary_box = f'<div class="summary-box">{trend_txt}</div>'
    else:
        right_chart = "<div class='no-data'>월별 추세 데이터가 없습니다.</div>"
        summary_box = ""

    return f"""
    <table class="sr-table">
        <tr>
            <td class="sr-col">
                <div class="sr-badge sr-spike">전주 대비 폭증 문의</div>
                {f'<div class="sr-sub">{escape(sub)}</div>' if sub else ''}
                {left_chart}
                {_build_heatmap(hourly)}
            </td>
            <td class="sr-col">
                <div class="sr-badge sr-spike">월별 폭증 문의</div>
                {right_chart}
                {summary_box}
            </td>
        </tr>
    </table>
    """


def _build_top5_section(top_requests: list[dict[str, Any]]) -> str:
    """유저 개선 요청 Top 5 — 설계 결함(좌) · 편의 개선(우)."""
    if not top_requests:
        return "<p class='no-data'>집계된 개선 요청이 없습니다.</p>"

    design = [r for r in top_requests if r.get("improvement_type") == "설계 결함"]
    ux = [r for r in top_requests if r.get("improvement_type") != "설계 결함"]

    def render_col(items: list[dict], cls: str) -> str:
        if not items:
            return "<div class='no-data'>해당 없음</div>"
        rows = ""
        for item in items:
            rank = escape(str(item.get("rank", "?")))
            cat = escape(str(item.get("category", "?")))
            kw = escape(" / ".join(item.get("topic_keywords") or []) or "—")
            cnt = int(item.get("count", 0))
            rows += f"""
            <li>
                <span class="rank rank-{cls}">{rank}</span>
                <div class="item-body">
                    <div class="item-cat">{cat}</div>
                    <div class="item-kw">{kw}</div>
                </div>
                <span class="item-cnt">{cnt:,}건</span>
            </li>
            """
        return f"<ul class='improve-list'>{rows}</ul>"

    return f"""
    <table class="improve-table">
        <tr>
            <th class="improve-head design-head">설계 결함</th>
            <th class="improve-head ux-head">편의 개선</th>
        </tr>
        <tr>
            <td class="improve-col">{render_col(design, 'design')}</td>
            <td class="improve-col">{render_col(ux, 'ux')}</td>
        </tr>
    </table>
    <div class="criteria-box">
        기준: 건수 × 심각도 가중합 (Nielsen 1994) — critical/high = 설계 결함, medium/low = 편의 개선
    </div>
    """


# ── HTML 조립 ──────────────────────────────────────────────────────────────────

def _build_html(report: dict[str, Any]) -> str:
    title = _text(report.get("title"), "운영 주간 보고서")
    gen_at = _text(report.get("generated_at"), "")[:10].replace("-", ".")
    window = report.get("window") or {}
    w_start = _text(window.get("window_start"), "?")[:10].replace("-", ".")
    w_end = _text(window.get("window_end"), "?")[:10].replace("-", ".")
    spike = report.get("spike_alerts") or {}
    top_requests = report.get("top_requests") or []

    return f"""
    <html>
    <head>
        <meta charset="utf-8" />
        <style>
            {_font_face_css()}
            @page {{
                size: A4;
                margin: 13mm 11mm 12mm 11mm;
            }}
            * {{ box-sizing: border-box; }}
            body {{
                font-family: '{FONT_FAMILY_NAME}', 'Segoe UI', Helvetica, Arial, sans-serif;
                background: #f0f2f5;
                color: #1a1a2e;
                font-size: 10pt;
                line-height: 1.45;
            }}
            table {{ width: 100%; border-collapse: collapse; }}

            /* ── 헤더 ── */
            .header {{
                background: #1e3a5f;
                color: #fff;
                padding: 16px 20px;
                margin-bottom: 12px;
            }}
            .header-inner {{ width: 100%; }}
            .header-left td {{ vertical-align: middle; padding: 0; }}
            .header-right td {{ text-align: right; vertical-align: middle; padding: 0; }}
            .eyebrow {{ font-size: 7.5pt; opacity: .7; letter-spacing: 1px; margin-bottom: 4px; color: #cbd5e1; }}
            .h-title {{ font-size: 17pt; font-weight: bold; color: #fff; }}
            .gen-date {{ font-size: 9pt; color: #cbd5e1; margin-bottom: 3px; }}
            .period {{ font-size: 11pt; font-weight: bold; color: #fff; }}

            /* ── 섹션 공통 ── */
            .sec-title {{
                font-size: 11pt; font-weight: bold; color: #1e3a5f;
                border-left: 4px solid #2d6a9f; padding-left: 8px; margin: 10px 0 7px;
            }}
            .card {{
                background: #fff;
                border: 1px solid #e5e7eb;
                padding: 14px 16px;
                margin-bottom: 10px;
                page-break-inside: avoid;
            }}

            /* ── AI 요약 ── */
            .ai-card {{ border-left: 4px solid #7c3aed; background: #faf5ff; }}
            .ai-badge {{
                display: inline-block; background: #7c3aed; color: #fff;
                font-size: 8pt; font-weight: bold; padding: 2px 7px; margin-bottom: 9px;
            }}
            .ai-cols-table {{ table-layout: fixed; }}
            .ai-col {{ width: 50%; padding: 0 8px 0 0; vertical-align: top; }}
            .ai-col:last-child {{ padding: 0 0 0 8px; border-left: 1px solid #ede9fe; }}
            .ai-col-title {{
                font-size: 8.5pt; font-weight: bold; color: #7c3aed; margin-bottom: 7px;
                text-transform: uppercase; letter-spacing: 0.5px;
            }}
            .ai-list {{ list-style: none; padding: 0; margin: 0; }}
            .ai-list li {{
                font-size: 9pt; padding: 3px 0; border-bottom: 1px solid #ede9fe;
                color: #3b3060; line-height: 1.5;
            }}
            .ai-list li:last-child {{ border-bottom: none; }}
            .ai-list li::before {{ content: "· "; color: #7c3aed; font-weight: bold; }}

            /* ── 카테고리 블록 ── */
            .m-row {{ table-layout: fixed; border-spacing: 4px; border-collapse: separate; }}
            .m-block {{
                background: #fff; border: 1px solid #e5e7eb;
                padding: 12px 6px; text-align: center; vertical-align: top;
            }}
            .m-cat {{ font-size: 8.5pt; font-weight: bold; color: #6b7280; margin-bottom: 6px; }}
            .m-count {{ font-size: 22pt; font-weight: 800; color: #1e3a5f; line-height: 1; margin-bottom: 6px; }}
            .badge-up {{
                display: inline-block; background: #fee2e2; color: #dc2626;
                font-size: 9pt; font-weight: bold; padding: 2px 8px;
            }}
            .badge-dn {{
                display: inline-block; background: #dcfce7; color: #16a34a;
                font-size: 9pt; font-weight: bold; padding: 2px 8px;
            }}
            .badge-eq {{
                display: inline-block; background: #f3f4f6; color: #6b7280;
                font-size: 9pt; font-weight: bold; padding: 2px 8px;
            }}
            .m-note {{ font-size: 7.5pt; color: #9ca3af; margin-top: 4px; }}

            /* ── 급증·위험 ── */
            .sr-table {{ table-layout: fixed; border-spacing: 6px; border-collapse: separate; }}
            .sr-col {{
                width: 50%; background: #fff; border: 1px solid #e5e7eb;
                padding: 12px 14px; vertical-align: top;
            }}
            .sr-badge {{
                display: inline-block; font-size: 8.5pt; font-weight: bold;
                padding: 2px 8px; margin-bottom: 7px;
            }}
            .sr-spike {{ background: #fff3cd; color: #b45309; }}
            .sr-sub {{ font-size: 8.5pt; color: #6b7280; margin-bottom: 8px; }}
            .heat-label {{ font-size: 8.5pt; font-weight: bold; color: #6b7280; margin: 8px 0 4px; }}
            .summary-box {{
                font-size: 9pt; color: #555; line-height: 1.8;
                padding: 9px 11px; background: #fffbf0;
                border-left: 3px solid #b45309; margin-top: 10px;
            }}
            .no-data {{ font-size: 9pt; color: #9ca3af; padding: 8px 0; }}
            .fb-table td {{ padding: 4px 6px; border-bottom: 1px solid #f3f4f6; font-size: 9pt; }}

            /* ── Top 5 ── */
            .improve-table {{ table-layout: fixed; border-spacing: 6px; border-collapse: separate; }}
            .improve-head {{
                font-size: 9.5pt; font-weight: bold; padding: 7px 10px;
                border-bottom: 2px solid;
            }}
            .design-head {{ color: #dc2626; border-color: #dc2626; background: #fff5f5; }}
            .ux-head {{ color: #2563eb; border-color: #2563eb; background: #eff6ff; }}
            .improve-col {{ width: 50%; background: #fff; border: 1px solid #e5e7eb; padding: 10px; vertical-align: top; }}
            .improve-list {{ list-style: none; padding: 0; margin: 0; }}
            .improve-list li {{
                display: block; padding: 5px 0;
                border-bottom: 1px solid #f3f4f6; font-size: 9pt; color: #374151;
            }}
            .improve-list li:last-child {{ border-bottom: none; }}
            .rank {{
                display: inline-block; width: 18px; height: 18px; line-height: 18px;
                text-align: center; font-size: 8pt; font-weight: bold;
                margin-right: 6px; vertical-align: middle;
            }}
            .rank-design {{ background: #fee2e2; color: #dc2626; }}
            .rank-ux {{ background: #dbeafe; color: #2563eb; }}
            .item-body {{ display: inline; }}
            .item-cat {{ display: inline; font-weight: bold; }}
            .item-kw {{ display: inline; font-size: 8pt; color: #9ca3af; margin-left: 4px; }}
            .item-cnt {{ float: right; font-size: 8.5pt; color: #9ca3af; }}
            .criteria-box {{
                font-size: 8pt; color: #9ca3af; line-height: 1.7;
                padding: 7px 10px; background: #f8f9fb;
                border: 1px solid #e5e7eb; margin-top: 8px;
            }}

            /* ── 푸터 ── */
            .footer {{ text-align: center; font-size: 8pt; color: #bbb; margin-top: 12px; }}
        </style>
    </head>
    <body>

        <!-- 헤더 -->
        <div class="header">
            <table class="header-inner">
                <tr>
                    <td>
                        <div class="eyebrow">WEEKLY OPERATIONS REPORT</div>
                        <div class="h-title">{escape(title)}</div>
                    </td>
                    <td style="text-align:right;vertical-align:middle;">
                        <div class="gen-date">생성 일자&nbsp;&nbsp;<strong>{escape(gen_at)}</strong></div>
                        <div class="period">분석 기간&nbsp;&nbsp;{escape(w_start)} ~ {escape(w_end)}</div>
                    </td>
                </tr>
            </table>
        </div>

        <!-- AI 요약 -->
        <div class="sec-title">AI 요약</div>
        <div class="card ai-card">
            {_build_ai_section(report)}
        </div>

        <!-- 주간 지표 -->
        <div class="sec-title">주간 지표 — 총 응대 건수</div>
        <div style="margin-bottom:10px;">
            {_build_category_blocks(report)}
        </div>

        <!-- 급증·위험 문의 현황 -->
        <div class="sec-title">급증·위험 문의 현황</div>
        {_build_spike_section(spike)}

        <!-- 유저 개선 요청 Top 5 -->
        <div class="sec-title">유저 개선 요청 Top 5</div>
        {_build_top5_section(top_requests)}

        <div class="footer">
            자동 생성 · {escape(gen_at)} &nbsp;|&nbsp; 분석 기준: {escape(w_start)} 00:00 ~ {escape(w_end)} 23:59
        </div>

    </body>
    </html>
    """


@observe_if_enabled(
    name="weekly_report_render_pdf",
    as_type="generation",
    tags=["weekly-report", "feature:pdf-render"],
)
def render_report_pdf(report: dict[str, Any]) -> bytes:
    link_weekly_report_trace(
        report,
        tags=["weekly-report", "feature:pdf-render"],
        input_payload={"title": report.get("title"), "generated_at": report.get("generated_at")},
        pdf_rendered=False,
        title=str(report.get("title") or ""),
    )
    html = _build_html(report)
    buffer = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8", link_callback=_resolve_resource_path)
    if result.err:
        raise RuntimeError("주간 리포트 PDF 렌더링에 실패했습니다")
    pdf_bytes = buffer.getvalue()
    link_weekly_report_trace(
        report,
        tags=["weekly-report", "feature:pdf-render"],
        output_payload={"pdf_bytes": len(pdf_bytes)},
        pdf_rendered=True,
        title=str(report.get("title") or ""),
    )
    return pdf_bytes
