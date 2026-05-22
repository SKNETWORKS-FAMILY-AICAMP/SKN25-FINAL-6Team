"""Unicode-safe PDF rendering helpers for the weekly dashboard report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PAGE_SIZE = (1240, 1754)
MARGIN_X = 72
MARGIN_Y = 72
LINE_HEIGHT = 26
SECTION_GAP = 18
TITLE_SIZE = 28
HEADER_SIZE = 20
BODY_SIZE = 16
TABLE_SIZE = 14


def _font_candidates() -> list[Path]:
    return [
        Path(r"C:\Windows\Fonts\malgunbd.ttf"),
        Path(r"C:\Windows\Fonts\malgun.ttf"),
        Path(r"C:\Windows\Fonts\malgunsl.ttf"),
    ]


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _font_candidates():
        if candidate.exists() and (not bold or "bd" in candidate.stem.lower()):
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
    text = text or ""
    if not text:
        return [""]
    words = text.split()
    if not words:
        words = [text]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    expanded: list[str] = []
    for line in lines:
        if not line:
            expanded.append("")
            continue
        segments = [line]
        while segments:
            segment = segments.pop(0)
            bbox = draw.textbbox((0, 0), segment, font=font)
            if bbox[2] - bbox[0] <= max_width:
                expanded.append(segment)
                continue
            if len(segment) <= 1:
                expanded.append(segment)
                continue
            midpoint = max(1, len(segment) // 2)
            segments.insert(0, segment[midpoint:])
            segments.insert(0, segment[:midpoint])
    return expanded or [""]


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: Any,
    x: int,
    y: int,
    max_width: int,
    fill: str = "#202124",
) -> int:
    for line in _wrap_text(draw, text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += LINE_HEIGHT
    return y


def render_report_pdf(report: dict[str, Any]) -> bytes:
    """Render the weekly report payload into a PDF byte stream."""

    pages: list[Image.Image] = []
    title_font = _load_font(TITLE_SIZE, bold=True)
    header_font = _load_font(HEADER_SIZE, bold=True)
    body_font = _load_font(BODY_SIZE)
    table_font = _load_font(TABLE_SIZE)

    lines: list[tuple[str, str]] = []
    lines.append(("title", report.get("title", "Dashboard Weekly Report")))
    lines.append(
        (
            "meta",
            f"Generated at {report.get('generated_at', '-')} | "
            f"Window {report.get('window', {}).get('window_start', '-')} ~ {report.get('window', {}).get('window_end', '-')}",
        )
    )
    lines.append(("meta", f"Previous window {report.get('previous_window', {}).get('window_start', '-')} ~ {report.get('previous_window', {}).get('window_end', '-')}"))
    lines.append(("blank", ""))
    lines.append(("heading", "Summary metrics"))
    summary = report.get("summary", {})
    summary_line = (
        f"analysis_count={summary.get('analysis_count', 0)} | "
        f"distinct_tickets={summary.get('distinct_ticket_count', 0)} | "
        f"high_risk_rate={summary.get('high_risk_rate', 0):.1%} | "
        f"negative_sentiment_rate={summary.get('negative_sentiment_rate', 0):.1%} | "
        f"human_review_rate={summary.get('human_review_rate', 0):.1%}"
    )
    lines.append(("body", summary_line))
    lines.append(("body", f"response_rate={summary.get('response_rate', 0):.1%} | analysis_coverage_rate={summary.get('analysis_coverage_rate', 0):.1%} | draft_coverage_rate={summary.get('draft_coverage_rate', 0):.1%}"))
    lines.append(("body", f"avg_query_length={summary.get('avg_query_length', '-'):.1f} | avg_summary_length={summary.get('avg_summary_length', '-'):.1f}" if summary.get("avg_query_length") is not None and summary.get("avg_summary_length") is not None else ""))

    lines.append(("blank", ""))
    lines.append(("heading", "Executive findings"))
    for item in report.get("narrative_insights", []):
        lines.append(("bullet", item))

    lines.append(("blank", ""))
    lines.append(("heading", "Column insights"))
    for item in report.get("column_insights", []):
        text = f"{item['column']}: {item['metric']} | {item['insight']}"
        lines.append(("bullet", text))

    lines.append(("blank", ""))
    lines.append(("heading", "Priority review tickets"))
    for row in report.get("review_rows", [])[:12]:
        lines.append(
            (
                "table",
                f"#{row.get('ticket_id')} | {row.get('category')} | {row.get('risk_level')} | "
                f"{row.get('routing_target')} | {str(row.get('summary') or '')[:120]}",
            )
        )

    lines.append(("blank", ""))
    lines.append(("heading", "Analysis detail sample"))
    headers = [
        "analysis_id",
        "ticket_id",
        "title",
        "status",
        "source_type",
        "category",
        "responder_type",
        "risk_level",
        "sentiment",
        "routing_target",
        "analyzed_at",
    ]
    lines.append(("table", " | ".join(headers)))
    for row in report.get("analysis_rows", [])[:20]:
        lines.append(
            (
                "table",
                " | ".join(
                    [
                        str(row.get("analysis_id") or "-"),
                        str(row.get("ticket_id") or "-"),
                        str(row.get("title") or "-")[:40],
                        str(row.get("status") or "-"),
                        str(row.get("source_type") or "-"),
                        str(row.get("category") or "-"),
                        str(row.get("responder_type") or "-"),
                        str(row.get("risk_level") or "-"),
                        str(row.get("sentiment") or "-"),
                        str(row.get("routing_target") or "-"),
                        str(row.get("analyzed_at") or "-"),
                    ]
                ),
            )
        )

    page_width, page_height = PAGE_SIZE
    max_text_width = page_width - (MARGIN_X * 2)
    y = MARGIN_Y
    current_page = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(current_page)

    def new_page() -> None:
        nonlocal current_page, draw, y
        pages.append(current_page)
        current_page = Image.new("RGB", PAGE_SIZE, "white")
        draw = ImageDraw.Draw(current_page)
        y = MARGIN_Y

    for kind, text in lines:
        if kind == "blank":
            y += SECTION_GAP
            continue

        font = body_font
        fill = "#202124"
        if kind == "title":
            font = title_font
            y += 4
        elif kind == "heading":
            font = header_font
            y += 8
            fill = "#111827"
        elif kind == "bullet":
            text = f"- {text}"
        elif kind == "table":
            font = table_font

        wrapped = _wrap_text(draw, text, font, max_text_width)
        needed_height = LINE_HEIGHT * len(wrapped)
        if y + needed_height + MARGIN_Y >= page_height:
            new_page()
            font = title_font if kind == "title" else header_font if kind == "heading" else font
            fill = "#202124" if kind not in {"heading"} else "#111827"
            if kind == "bullet":
                text = f"- {text[2:]}" if text.startswith("- ") else text
            wrapped = _wrap_text(draw, text, font, max_text_width)
        for line in wrapped:
            draw.text((MARGIN_X, y), line, font=font, fill=fill)
            y += LINE_HEIGHT

    pages.append(current_page)

    buffer = __import__("io").BytesIO()
    if len(pages) == 1:
        pages[0].save(buffer, format="PDF")
    else:
        pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()

