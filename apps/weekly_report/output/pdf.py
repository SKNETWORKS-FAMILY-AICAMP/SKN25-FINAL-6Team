"""HTML/CSS 기반 주간 리포트 PDF 렌더링."""

from __future__ import annotations

import base64
import os
from html import escape
from pathlib import Path
from typing import Any

from weasyprint import HTML


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
                notable.append((abs(pct), f"{cat} {abs(pct):.0f}% {word}"))
    for _, txt in sorted(notable, reverse=True)[:2]:
        bullets.append(txt)

    spike = report.get("spike_alerts") or {}
    anomaly = [d for d in (spike.get("daily") or []) if d.get("level") != "normal"]
    if anomaly:
        w = max(anomaly, key=lambda x: x.get("pct_change", 0))
        bullets.append(f"{w.get('day', '?')} {w.get('pct_change', 0)*100:+.0f}% 폭증")

    critical_h = [h for h in (spike.get("hourly") or []) if h.get("level") == "critical"]
    if critical_h:
        times = ", ".join(f"{h['hour']:02d}시" for h in critical_h[:3])
        bullets.append(f"위험 시간: {times}")

    return bullets[:5] if bullets else ["특이 사항 없음"]


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
            li(f"{a.get('category','')} · {a.get('action','')}")
            for a in actions[:3]
        )
    else:
        right_items = "<li>권장 액션 없음</li>"

    return f"""
    <div class="ai-badge">AI SUMMARY</div>
    <table class="ai-cols-table">
        <tr>
            <td class="ai-col" style="width:42%;">
                <div class="ai-col-title">주간 지표 요약</div>
                <ul class="ai-list">{left_items}</ul>
            </td>
            <td class="ai-col" style="width:58%;">
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
                note = "전주 대비 증가"
            elif pct < -5:
                badge_cls = "badge-dn"
                arrow = "▼"
                note = "전주 대비 감소"
            else:
                badge_cls = "badge-eq"
                arrow = "→"
                note = "전주 동일"
            badge_html = f'<div><span class="{badge_cls}">{arrow} {abs(pct):.0f}%</span></div>'
        else:
            badge_html = '<div><span class="badge-eq">— </span></div>'
            note = "비교 없음"

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
            bg, fg = "#dc2626", "#ffffff"
        elif level == "warning":
            bg, fg = "#ef4444", "#ffffff"
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
        '<span style="color:#dc2626;font-weight:bold;">■ 위험(Z≥3)</span>&nbsp;&nbsp;'
        '<span style="color:#ef4444;font-weight:bold;">■ 경고(Z≥2)</span>&nbsp;&nbsp;'
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
            "#dc2626" if r.get("level") == "critical" else
            "#ef4444" if r.get("level") == "warning" else
            "rgba(220,38,38,0.35)"
            for r in daily
        ]
        uri = _make_bar_chart_png(labels, values, colors, width=440, height=195)
        left_chart = (
            f'<img style="width:100%;height:auto;" src="{uri}" />'
            if uri else
            "<table class='fb-table'>" +
            "".join(f"<tr><td>{escape(r.get('day',''))}</td><td>{int(r.get('this_week',0)):,}건</td></tr>" for r in daily) +
            "</table>"
        )
        anomaly = [d for d in daily if d.get("level") != "normal"]
        sub = (
            "폭증: " + ", ".join(f"{d['day']} {d['pct_change']*100:+.0f}%({d['level']})" for d in anomaly)
            if anomaly else "일별 폭증 없음"
        )
    else:
        left_chart = "<div class='no-data'>일별 데이터 없음</div>"
        sub = ""

    # ── 우: 4주 바차트 + 요약 ──
    if monthly:
        labels_m = [r.get("label", "?") for r in monthly]
        values_m = [float(r.get("count", 0)) for r in monthly]
        colors_m = [
            "rgba(220,38,38,0.80)",
            "rgba(220,38,38,0.60)",
            "rgba(220,38,38,0.40)",
            "rgba(220,38,38,0.20)",
        ][:len(values_m)]
        uri_m = _make_bar_chart_png(labels_m, values_m, colors_m, width=400, height=195)
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
                trend_txt = f"이번 주 <strong>{this_w:,}건</strong> (전주 대비 {pct:+.1f}%)"
            else:
                trend_txt = f"이번 주 <strong>{this_w:,}건</strong>"
        else:
            trend_txt = "데이터 없음"
        summary_box = f'<div class="summary-box">{trend_txt}</div>'
    else:
        right_chart = "<div class='no-data'>월별 데이터 없음</div>"
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
    """유저 개선 요청 Top 5 — 5칸 고정 테이블."""
    rows_html = ""
    for i in range(5):
        even_cls = " top5-even" if i % 2 == 1 else ""
        if i < len(top_requests):
            item = top_requests[i]
            rank = i + 1
            cat = escape(str(item.get("category", "?")))
            kw = escape(" / ".join(item.get("topic_keywords") or []) or "—")
            cnt = int(item.get("count", 0))
            imp_type = item.get("improvement_type", "")
            if imp_type == "설계 결함":
                type_cls, type_label = "type-design", "설계 결함"
            else:
                type_cls, type_label = "type-ux", "편의 개선"
            rows_html += f"""
            <tr class="top5-row{even_cls}">
                <td class="top5-rank">{rank}</td>
                <td class="top5-type"><span class="type-badge {type_cls}">{type_label}</span></td>
                <td class="top5-cat">{cat}</td>
                <td class="top5-kw">{kw}</td>
                <td class="top5-cnt">{cnt:,}건</td>
            </tr>
            """
        else:
            rows_html += f"""
            <tr class="top5-row top5-empty{even_cls}">
                <td class="top5-rank">—</td>
                <td class="top5-type"></td>
                <td class="top5-cat">—</td>
                <td class="top5-kw"></td>
                <td class="top5-cnt">—</td>
            </tr>
            """

    return f"""
    <table class="top5-table">
        <thead>
            <tr>
                <th class="top5-th" style="width:6%;">순위</th>
                <th class="top5-th" style="width:16%;">유형</th>
                <th class="top5-th" style="width:18%;">카테고리</th>
                <th class="top5-th">키워드</th>
                <th class="top5-th" style="width:10%;">건수</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
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
                margin: 7mm 9mm 10mm 9mm;
                @bottom-center {{
                    content: element(page-footer);
                }}
            }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            html, body {{ height: 100%; }}
            body {{
                font-family: '{FONT_FAMILY_NAME}', 'Segoe UI', Helvetica, Arial, sans-serif;
                background: #f0f2f5;
                color: #1a1a2e;
                font-size: 9pt;
                line-height: 1.35;
                letter-spacing: 0.1px;
                display: flex;
                flex-direction: column;
            }}
            table {{ width: 100%; border-collapse: collapse; }}

            /* ── 푸터 (페이지 끝 고정) ── */
            .page-footer {{
                position: running(page-footer);
                text-align: center;
                font-size: 7.5pt;
                color: #bbb;
            }}

            /* ── 헤더 ── */
            .header {{
                background: #1e3a5f;
                color: #fff;
                padding: 16px 16px;
            }}
            .header-inner {{ width: 100%; }}
            .eyebrow {{ font-size: 7pt; opacity: .7; letter-spacing: 1px; margin-bottom: 3px; color: #cbd5e1; }}
            .h-title {{ font-size: 20pt; font-weight: bold; color: #fff; letter-spacing: 0.5px; }}
            .gen-date {{ font-size: 8pt; color: #cbd5e1; margin-bottom: 2px; }}
            .period {{ font-size: 10pt; font-weight: bold; color: #fff; }}

            /* ── 메인: 위에서부터 고정 간격 ── */
            .main-content {{
                display: block;
                padding: 6px 0 0;
            }}
            .section-block {{ margin-bottom: 9px; }}

            /* ── 섹션 공통 ── */
            .sec-title {{
                font-size: 9.5pt; font-weight: bold; color: #1e3a5f;
                border-left: 3px solid #2563eb; padding-left: 6px; margin-bottom: 6px;
            }}
            .card {{
                background: #fff;
                border: 1px solid #e5e7eb;
                padding: 12px 12px;
                page-break-inside: avoid;
            }}

            /* ── AI 요약 ── */
            .ai-card {{ border-left: 3px solid #2563eb; background: #eff6ff; }}
            .ai-badge {{
                display: inline-block; background: #2563eb; color: #fff;
                font-size: 7pt; font-weight: bold; padding: 1px 6px; margin-bottom: 4px;
            }}
            .ai-cols-table {{ table-layout: fixed; }}
            .ai-col {{ width: 50%; padding: 0 6px 0 0; vertical-align: top; }}
            .ai-col:last-child {{ padding: 0 0 0 6px; border-left: 1px solid #dbeafe; }}
            .ai-col-title {{
                font-size: 7.5pt; font-weight: bold; color: #2563eb; margin-bottom: 3px;
                text-transform: uppercase; letter-spacing: 0.5px;
            }}
            .ai-list {{ list-style: none; padding: 0; margin: 0; }}
            .ai-list li {{
                font-size: 8pt; padding: 4px 0; border-bottom: 1px solid #dbeafe;
                color: #374151; line-height: 1.35;
            }}
            .ai-list li:last-child {{ border-bottom: none; }}
            .ai-list li::before {{ content: "· "; color: #2563eb; font-weight: bold; }}

            /* ── 카테고리 블록 ── */
            .m-row {{ table-layout: fixed; border-spacing: 3px; border-collapse: separate; }}
            .m-block {{
                background: #fff; border: 1px solid #e5e7eb;
                padding: 16px 4px; text-align: center; vertical-align: middle;
            }}
            .m-cat {{ font-size: 8pt; font-weight: bold; color: #6b7280; margin-bottom: 5px; }}
            .m-count {{ font-size: 21pt; font-weight: 800; color: #1e3a5f; line-height: 1; margin-bottom: 5px; }}
            .badge-up {{
                display: inline-block; background: #fee2e2; color: #dc2626;
                font-size: 8pt; font-weight: bold; padding: 1px 6px;
            }}
            .badge-dn {{
                display: inline-block; background: #dbeafe; color: #2563eb;
                font-size: 8pt; font-weight: bold; padding: 1px 6px;
            }}
            .badge-eq {{
                display: inline-block; background: #f3f4f6; color: #6b7280;
                font-size: 8pt; font-weight: bold; padding: 1px 6px;
            }}
            .m-note {{ font-size: 7pt; color: #9ca3af; margin-top: 2px; }}

            /* ── 급증·위험 ── */
            .sr-table {{ table-layout: fixed; border-spacing: 4px; border-collapse: separate; }}
            .sr-col {{
                width: 50%; background: #fff; border: 1px solid #e5e7eb;
                padding: 10px 12px; vertical-align: top;
            }}
            .sr-badge {{
                display: inline-block; font-size: 7.5pt; font-weight: bold;
                padding: 1px 6px; margin-bottom: 4px;
            }}
            .sr-spike {{ background: #fee2e2; color: #dc2626; }}
            .sr-sub {{ font-size: 7.5pt; color: #6b7280; margin-bottom: 4px; }}
            .heat-label {{ font-size: 7.5pt; font-weight: bold; color: #6b7280; margin: 5px 0 2px; }}
            .summary-box {{
                font-size: 8pt; color: #555; line-height: 1.5;
                padding: 4px 8px; background: #fff5f5;
                border-left: 3px solid #dc2626; margin-top: 5px;
            }}
            .no-data {{ font-size: 8pt; color: #9ca3af; padding: 4px 0; }}
            .fb-table td {{ padding: 3px 5px; border-bottom: 1px solid #f3f4f6; font-size: 8pt; }}

            /* ── Top 5 ── */
            .top5-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
            .top5-th {{
                background: #f3f4f6; color: #6b7280;
                font-size: 7.5pt; font-weight: bold;
                padding: 10px 10px; text-align: left;
                border-bottom: 2px solid #e5e7eb;
                text-transform: uppercase; letter-spacing: 0.4px;
            }}
            .top5-row td {{
                padding: 7px 10px; border-bottom: 1px solid #f3f4f6;
                vertical-align: middle; height: 30px;
                background: #fff;
            }}
            .top5-row:last-child td {{ border-bottom: none; }}
            .top5-even td {{ background: #fafafa; }}
            .top5-empty td {{ color: #d1d5db; font-size: 8pt; background: #fff; }}
            .top5-rank {{
                font-size: 11pt; font-weight: 800; color: #1e3a5f;
                text-align: center; width: 6%;
            }}
            .top5-empty .top5-rank {{ color: #e5e7eb; font-size: 10pt; }}
            .top5-type {{ width: 16%; }}
            .top5-cat {{ font-size: 8pt; font-weight: bold; color: #1a1a2e; width: 18%; }}
            .top5-kw {{ font-size: 7pt; color: #9ca3af; }}
            .top5-cnt {{ font-size: 8pt; font-weight: bold; color: #374151; text-align: right; width: 10%; }}
            .type-badge {{
                display: inline-block; font-size: 7.5pt; font-weight: bold;
                padding: 2px 8px; letter-spacing: 0.2px;
            }}
            .type-design {{ background: #fee2e2; color: #dc2626; }}
            .type-ux {{ background: #dbeafe; color: #2563eb; }}
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

        <!-- 메인: flex로 4섹션이 페이지 높이를 균등 점유 -->
        <div class="main-content">

            <div class="section-block sec-ai">
                <div class="sec-title">AI 요약</div>
                <div class="card ai-card">
                    {_build_ai_section(report)}
                </div>
            </div>

            <div class="section-block sec-metrics">
                <div class="sec-title">주간 지표 — 총 응대 건수</div>
                {_build_category_blocks(report)}
            </div>

            <div class="section-block sec-spike">
                <div class="sec-title">급증·위험 문의 현황</div>
                {_build_spike_section(spike)}
            </div>

            <div class="section-block sec-top5">
                <div class="sec-title">유저 개선 요청 Top 5</div>
                <div class="card">
                    {_build_top5_section(top_requests)}
                </div>
            </div>

        </div>

        <!-- 푸터: @page @bottom-center에 의해 페이지 끝에 배치 -->
        <div class="page-footer">
            자동 생성 · {escape(gen_at)} &nbsp;|&nbsp; 분석 기준: {escape(w_start)} 00:00 ~ {escape(w_end)} 23:59
        </div>

    </body>
    </html>
    """


def render_report_pdf(report: dict[str, Any]) -> bytes:
    html = _build_html(report)
    return HTML(string=html).write_pdf()
