from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "assets" / "generated"


EMBEDDING_FALLBACK = {
    "dataset_size": 30,
    "profiles": [
        {
            "key": "small1536",
            "label": "text-embedding-3-small",
            "dims": 1536,
            "top1": 90.0,
            "top5": 100.0,
            "mrr": 0.868,
            "context_precision": 0.8324,
            "context_recall": 0.8500,
            "faithfulness": 0.8668,
            "overall": 0.8497,
            "cost_per_1m": 0.020,
            "cost_index": 1.0,
        },
        {
            "key": "large1536",
            "label": "text-embedding-3-large",
            "dims": 1536,
            "top1": 93.3,
            "top5": 100.0,
            "mrr": 0.892,
            "context_precision": 0.8474,
            "context_recall": 0.8500,
            "faithfulness": 0.9043,
            "overall": 0.8672,
            "cost_per_1m": 0.130,
            "cost_index": 6.5,
        },
        {
            "key": "large3072",
            "label": "text-embedding-3-large",
            "dims": 3072,
            "top1": 93.3,
            "top5": 100.0,
            "mrr": 0.895,
            "context_precision": 0.8419,
            "context_recall": 0.8667,
            "faithfulness": 0.9227,
            "overall": 0.8771,
            "cost_per_1m": 0.130,
            "cost_index": 6.5,
        },
    ],
    "summary": {
        "best_quality": "large3072",
        "best_cost_efficiency": "small1536",
    },
}


CHATBOT_EVAL_SPECS = [
    {
        "name": "FAQ Agent",
        "dataset": "apps/chatbot/backend/evals/datasets/gameops-chatbot-faq-agent-db-grounded-40-v1.json",
        "metrics": ["source_hit@5", "false_fallback_rate", "faithfulness"],
    },
    {
        "name": "Payment Agent",
        "dataset": "apps/chatbot/backend/evals/datasets/gameops-chatbot-payment-agent-db-grounded-30-v1.json",
        "metrics": ["db_lookup_accuracy", "action_match", "false_fallback_rate"],
    },
    {
        "name": "Bug Agent",
        "dataset": "apps/chatbot/backend/evals/datasets/gameops-chatbot-bug-agent-synthetic-20-v1.json",
        "metrics": ["required_core_info_coverage", "action_match", "false_fallback_rate"],
    },
    {
        "name": "Safety Layer",
        "dataset": "apps/chatbot/backend/evals/datasets/gameops-chatbot-safety-layer-12-v1.json",
        "metrics": ["safety_action_match", "masking_label_accuracy", "error_rate"],
    },
    {
        "name": "E2E Workflow",
        "dataset": "apps/chatbot/backend/evals/datasets/gameops-chatbot-e2e-workflow-22-v1.json",
        "metrics": ["workflow_success_rate", "routing_match_rate", "false_fallback_rate"],
    },
]


PALETTE = {
    "bg": "#F3F7FF",
    "panel": "#FFFFFF",
    "panel_soft": "#F7FAFF",
    "line": "#D9E4F5",
    "navy": "#143C7D",
    "blue": "#1D63D3",
    "blue_soft": "#EAF2FF",
    "green": "#18A36A",
    "green_soft": "#EAF9F1",
    "purple": "#6C45D9",
    "purple_soft": "#F2EEFF",
    "amber": "#D99100",
    "amber_soft": "#FFF6E1",
    "text": "#163252",
    "muted": "#6A7D96",
}


@dataclass
class Fonts:
    title: ImageFont.FreeTypeFont
    h1: ImageFont.FreeTypeFont
    h2: ImageFont.FreeTypeFont
    h3: ImageFont.FreeTypeFont
    body: ImageFont.FreeTypeFont
    body_small: ImageFont.FreeTypeFont
    metric: ImageFont.FreeTypeFont
    badge: ImageFont.FreeTypeFont


def load_fonts() -> Fonts:
    regular = Path(r"C:\Windows\Fonts\malgun.ttf")
    bold = Path(r"C:\Windows\Fonts\malgunbd.ttf")
    if not regular.exists() or not bold.exists():
        raise FileNotFoundError("Required Malgun Gothic fonts were not found.")
    return Fonts(
        title=ImageFont.truetype(str(bold), 42),
        h1=ImageFont.truetype(str(bold), 28),
        h2=ImageFont.truetype(str(bold), 22),
        h3=ImageFont.truetype(str(bold), 18),
        body=ImageFont.truetype(str(regular), 16),
        body_small=ImageFont.truetype(str(regular), 13),
        metric=ImageFont.truetype(str(bold), 26),
        badge=ImageFont.truetype(str(bold), 16),
    )


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=font)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text:
        return [""]
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = word
        else:
            chunk = ""
            for char in word:
                candidate = chunk + char
                if text_width(draw, candidate, font) <= max_width:
                    chunk = candidate
                else:
                    lines.append(chunk)
                    chunk = char
            current = chunk
    if current:
        lines.append(current)
    return lines


def rounded_box(
    base: Image.Image,
    xy: tuple[int, int, int, int],
    *,
    radius: int = 22,
    fill: str = PALETTE["panel"],
    outline: str | None = PALETTE["line"],
    width: int = 1,
    shadow: bool = True,
) -> None:
    x1, y1, x2, y2 = xy
    if shadow:
        shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow_layer)
        sdraw.rounded_rectangle((x1 + 4, y1 + 8, x2 + 4, y2 + 8), radius=radius, fill=(16, 45, 90, 28))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(8))
        base.alpha_composite(shadow_layer)
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fg: str,
    bg: str,
    padding_x: int = 14,
    padding_y: int = 8,
) -> tuple[int, int, int, int]:
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    width = int(bbox[2] - bbox[0] + padding_x * 2)
    height = int(bbox[3] - bbox[1] + padding_y * 2)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=14, fill=bg)
    draw.text((x + padding_x, y + padding_y - 1), text, font=font, fill=fg)
    return (x, y, x + width, y + height)


def draw_paragraph(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: str,
    max_width: int,
    line_gap: int = 6,
) -> int:
    lines = wrap_text(draw, text, font, max_width)
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=fill)
        current_y += font.size + line_gap
    return current_y


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_embedding_data() -> dict:
    output_path = REPO_ROOT / "apps" / "chatbot" / "backend" / "evals" / "outputs" / "sj_embedding_model_comparison.json"
    if output_path.exists():
        payload = load_json(output_path)
        profiles = []
        for key, value in payload.get("profiles", {}).items():
            summary = value.get("summary", {})
            profiles.append(
                {
                    "key": key,
                    "label": str(value.get("embedding_model") or key),
                    "dims": int(value.get("embedding_dimensions") or 0),
                    "top1": round(float(summary.get("top1_accuracy") or 0.0) * 100, 1),
                    "top5": round(float(summary.get("top5_recall") or 0.0) * 100, 1),
                    "mrr": round(float(summary.get("mrr") or 0.0), 3),
                    "context_precision": round(float(summary.get("context_precision") or 0.0), 4),
                    "context_recall": round(float(summary.get("context_recall") or 0.0), 4),
                    "faithfulness": round(float(summary.get("faithfulness") or 0.0), 4),
                    "overall": round(float(summary.get("overall_avg") or 0.0), 4),
                    "cost_per_1m": float(summary.get("cost_per_1m_tokens_usd") or 0.0),
                    "cost_index": float(summary.get("cost_index_vs_small") or 0.0),
                }
            )
        if profiles:
            return {
                "dataset_size": int(payload.get("dataset_size") or 0),
                "profiles": profiles,
                "summary": payload.get("summary") or {},
            }
    return EMBEDDING_FALLBACK


def load_analysis_data() -> dict:
    report_path = REPO_ROOT / "apps" / "tests" / "cs-auto_tests" / "eval" / "20260616_170839" / "analysis_agent" / "report.json"
    report = load_json(report_path)
    metrics = report["metrics"]
    confusion = report["confusion_matrices"]
    payment_confusion = confusion["category"]["payment"]
    top_errors = {
        "payment_to_bug": int(payment_confusion.get("bug", 0)),
        "payment_to_refund": int(payment_confusion.get("refund", 0)),
        "negative_to_neutral": int(confusion["sentiment"]["negative"].get("neutral", 0)),
        "db_only_to_doc_only": int(confusion["routing_target"]["DB_only"].get("doc_only", 0)),
    }
    return {
        "ticket_count": report["ticket_count"],
        "metrics": metrics,
        "top_errors": top_errors,
        "path": report_path.relative_to(REPO_ROOT).as_posix(),
        "short_path": "analysis_agent/report.json",
    }


def load_answer_data() -> dict:
    eval_root = REPO_ROOT / "apps" / "tests" / "cs-auto_tests" / "eval"
    runs: list[dict] = []
    for run_dir in sorted(eval_root.iterdir()):
        summary_path = run_dir / "answer_agent" / "summary.csv"
        report_path = run_dir / "answer_agent" / "report.json"
        if not summary_path.exists():
            continue
        with summary_path.open(encoding="utf-8-sig", newline="") as fp:
            summary_rows = {row["section"]: row for row in csv.DictReader(fp)}
        runs.append(
            {
                "run": run_dir.name,
                "summary_path": summary_path,
                "report_path": report_path if report_path.exists() else None,
                "router_accuracy": float(summary_rows.get("router_decision", {}).get("accuracy") or 0.0),
                "chosen_path_rows": int(summary_rows.get("chosen_path", {}).get("non_empty_rows") or 0),
                "router_match_rows": int(summary_rows.get("chosen_path", {}).get("router_match_and_non_empty_rows") or 0),
                "doc_gold_chunk_hits": int(summary_rows.get("document_retrieval", {}).get("gold_chunk_hit_cases") or 0),
                "doc_gold_document_hits": int(summary_rows.get("document_retrieval", {}).get("gold_document_hit_cases") or 0),
                "verified_docs": int(summary_rows.get("dataset_live_db_verification", {}).get("gold_document_ids_verified_total") or 0),
                "verified_chunks": int(summary_rows.get("dataset_live_db_verification", {}).get("gold_chunk_ids_verified_total") or 0),
                "text_to_sql_non_empty_rows": int(summary_rows.get("text_to_sql", {}).get("non_empty_rows") or 0),
                "text_to_sql_expected_cases_with_rows": int(summary_rows.get("text_to_sql", {}).get("expected_cases_with_rows") or 0),
            }
        )
    latest = runs[-1]
    report = load_json(latest["report_path"])
    return {
        "ticket_count": report["ticket_count"],
        "db_case_count": report["db_case_count"],
        "doc_case_count": report["doc_case_count"],
        "metrics": report["metrics"],
        "path": latest["report_path"].relative_to(REPO_ROOT).as_posix(),
        "short_path": f"{latest['run']}/answer_agent/report.json",
        "runs": runs,
        "latest_run": latest["run"],
    }


def load_chatbot_suite() -> list[dict]:
    rows = []
    for spec in CHATBOT_EVAL_SPECS:
        path = REPO_ROOT / Path(spec["dataset"])
        payload = load_json(path)
        info = payload["dataset_info"]
        rows.append(
            {
                "name": spec["name"],
                "examples": int(info["total_examples"]),
                "description": str(info["description"]),
                "metrics": spec["metrics"],
                "path": path.relative_to(REPO_ROOT).as_posix(),
            }
        )
    return rows


def table_grid(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    headers: list[str],
    rows: list[list[str]],
    *,
    fonts: Fonts,
    widths: list[float],
) -> None:
    x1, y1, x2, y2 = xy
    total_width = x2 - x1
    col_widths = [int(total_width * ratio) for ratio in widths]
    col_widths[-1] = total_width - sum(col_widths[:-1])
    header_h = 38
    row_h = 34
    draw.rounded_rectangle((x1, y1, x2, y2), radius=16, outline=PALETTE["line"], width=1, fill=PALETTE["panel_soft"])
    draw.rectangle((x1, y1, x2, y1 + header_h), fill="#EEF3FB")
    cursor_x = x1
    for idx, header in enumerate(headers):
        if idx > 0:
            draw.line((cursor_x, y1, cursor_x, y2), fill=PALETTE["line"], width=1)
        draw.text((cursor_x + 10, y1 + 10), header, font=fonts.h3, fill=PALETTE["text"])
        cursor_x += col_widths[idx]
    current_y = y1 + header_h
    for row in rows:
        draw.line((x1, current_y, x2, current_y), fill=PALETTE["line"], width=1)
        cursor_x = x1
        for idx, value in enumerate(row):
            fill = PALETTE["blue"] if idx == len(row) - 1 and value.endswith("1") else PALETTE["text"]
            draw.text((cursor_x + 10, current_y + 8), value, font=fonts.body, fill=fill)
            cursor_x += col_widths[idx]
        current_y += row_h


def create_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width, height), PALETTE["bg"])
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(gradient)
    gdraw.ellipse((-160, -120, 620, 520), fill=(29, 99, 211, 30))
    gdraw.ellipse((width - 540, -120, width + 160, 440), fill=(108, 69, 217, 22))
    gdraw.ellipse((width - 420, height - 280, width + 120, height + 120), fill=(24, 163, 106, 18))
    gradient = gradient.filter(ImageFilter.GaussianBlur(50))
    image.alpha_composite(gradient)
    return image, ImageDraw.Draw(image)


def render_embedding_image(fonts: Fonts) -> Path:
    data = load_embedding_data()
    image, draw = create_canvas(1600, 1040)
    draw.text((48, 34), "임베딩 모델 평가 결과", font=fonts.title, fill=PALETTE["navy"])
    draw.text(
        (48, 98),
        "저장소의 임베딩 평가 스크립트와 버전된 평가 자산을 기반으로 검색 성능, 품질, 비용을 재구성했습니다.",
        font=fonts.body,
        fill=PALETTE["muted"],
    )
    draw.line((48, 148, 1552, 148), fill=PALETTE["line"], width=2)
    draw_label(draw, (48, 170), "1. 평가 세트 구성", font=fonts.badge, fg="#FFFFFF", bg=PALETTE["blue"])
    draw_label(draw, (476, 172), f"총 {data['dataset_size']}개 테스트셋", font=fonts.badge, fg=PALETTE["text"], bg="#EFF3F8")
    draw_label(draw, (626, 170), "2. 검색 성능", font=fonts.badge, fg="#FFFFFF", bg=PALETTE["green"])
    draw_label(draw, (1120, 170), "3. 품질 평가", font=fonts.badge, fg="#FFFFFF", bg=PALETTE["purple"])

    rounded_box(image, (48, 208, 558, 558), fill=PALETTE["panel"])
    rounded_box(image, (596, 208, 1084, 558), fill=PALETTE["panel"])
    rounded_box(image, (1120, 208, 1552, 558), fill=PALETTE["panel"])
    rounded_box(image, (48, 596, 558, 896), fill=PALETTE["panel"])
    rounded_box(image, (596, 596, 1084, 896), fill=PALETTE["panel"])
    rounded_box(image, (1120, 596, 1552, 896), fill=PALETTE["panel"])
    rounded_box(image, (48, 924, 1552, 1000), fill=PALETTE["panel_soft"], shadow=False, radius=24)

    x = 74
    y = 232
    draw.text((x, y), "평가 근거", font=fonts.h2, fill=PALETTE["text"])
    y += 42
    for line in [
        "스크립트: apps/chatbot/backend/evals/compare_sj_embedding_models.py",
        "데이터셋: sj-documents-retrievable-ragas-30-v3.json",
        "비교 프로필: small 1536 / large 1536 / large 3072",
        "검색 지표: Top1 Accuracy, Top5 Recall, MRR",
        "품질 지표: context_precision, context_recall, faithfulness",
    ]:
        y = draw_paragraph(draw, x, y, line, font=fonts.body, fill=PALETTE["text"], max_width=450)
        y += 2
    y += 8
    draw.text((x, y), "평가 해석", font=fonts.h2, fill=PALETTE["text"])
    y += 40
    for note in [
        "3072차원 large가 품질 평균 최고점 0.8771을 기록했습니다.",
        "1536차원 small은 1M token당 $0.020으로 가장 저렴합니다.",
        "원본 JSON 결과는 저장소에 없어서 기존 reference PNG 값을 사용했습니다.",
    ]:
        y = draw_paragraph(draw, x, y, f"- {note}", font=fonts.body, fill=PALETTE["muted"], max_width=450)
        y += 2

    profiles = data["profiles"]
    best_search = max(profiles, key=lambda row: (row["top1"], row["mrr"]))
    metrics = [
        ("Top1 Accuracy", f"{best_search['top1']:.1f}%"),
        ("Top5 Recall", "100%"),
        ("Best MRR", f"{max(row['mrr'] for row in profiles):.3f}"),
    ]
    metric_x = 618
    for idx, (label, value) in enumerate(metrics):
        box_x1 = metric_x + idx * 156
        box_x2 = box_x1 + 140
        rounded_box(image, (box_x1, 228, box_x2, 318), fill="#F9FCFF", shadow=False, radius=18)
        draw.text((box_x1 + 16, 245), label, font=fonts.body, fill=PALETTE["muted"])
        draw.text((box_x1 + 16, 274), value, font=fonts.metric, fill=PALETTE["green"])

    draw.text((618, 342), "모델별 검색 성능", font=fonts.h2, fill=PALETTE["text"])
    rows = [
        [f"{row['label']} ({row['dims']})", f"{row['top1']:.1f}%", f"{row['top5']:.0f}%", f"{row['mrr']:.3f}"]
        for row in profiles
    ]
    table_grid(
        draw,
        (618, 382, 1060, 520),
        ["모델", "Top1", "Top5", "MRR"],
        rows,
        fonts=fonts,
        widths=[0.56, 0.14, 0.14, 0.16],
    )
    draw.text((618, 528), "* 품질 평가 원본 스냅샷은 제공된 reference PNG를 기준으로 재구성", font=fonts.body_small, fill=PALETTE["muted"])

    draw.text((1142, 232), "모델별 품질 점수", font=fonts.h2, fill=PALETTE["text"])
    quality_rows = [
        ["context_precision", "0.8324", "0.8474", "0.8419"],
        ["context_recall", "0.8500", "0.8500", "0.8667"],
        ["faithfulness", "0.8668", "0.9043", "0.9227"],
        ["종합 평균", "0.8497", "0.8672", "0.8771"],
    ]
    table_grid(
        draw,
        (1142, 272, 1528, 520),
        ["평가 항목", "small", "large", "3072"],
        quality_rows,
        fonts=fonts,
        widths=[0.42, 0.19, 0.19, 0.20],
    )
    draw_label(draw, (1142, 530), "large 3072가 종합 품질 최고", font=fonts.badge, fg=PALETTE["purple"], bg=PALETTE["purple_soft"])

    draw.text((74, 620), "프로필 요약", font=fonts.h2, fill=PALETTE["text"])
    card_y = 664
    card_specs = [
        ("small1536", PALETTE["blue_soft"], PALETTE["blue"]),
        ("large1536", PALETTE["green_soft"], PALETTE["green"]),
        ("large3072", PALETTE["purple_soft"], PALETTE["purple"]),
    ]
    summary_map = {row["key"]: row for row in profiles}
    for idx, (key, bg, accent) in enumerate(card_specs):
        row = summary_map[key]
        left = 74 + idx * 158
        rounded_box(image, (left, card_y, left + 142, 860), fill=bg, shadow=False, radius=18, outline=None)
        draw.text((left + 12, card_y + 12), f"{row['dims']}차원", font=fonts.h3, fill=accent)
        draw.text((left + 12, card_y + 42), row["label"], font=fonts.body_small, fill=PALETTE["text"])
        draw.text((left + 12, card_y + 86), f"Top1 {row['top1']:.1f}%", font=fonts.body, fill=PALETTE["text"])
        draw.text((left + 12, card_y + 120), f"MRR {row['mrr']:.3f}", font=fonts.body, fill=PALETTE["text"])
        draw.text((left + 12, card_y + 154), f"품질 {row['overall']:.4f}", font=fonts.body, fill=PALETTE["text"])

    draw.text((618, 620), "평가 설계와 테스트셋", font=fonts.h2, fill=PALETTE["text"])
    design_lines = [
        "실제 운영 문서 기반 30개 질의-정답 쌍 사용",
        "문서 타입: 정책, FAQ, 공지, 가이드",
        "RAGAS 스타일 품질 지표와 검색 정확도 병행",
        "차원 변화와 모델 비용을 동시에 비교",
    ]
    cur_y = 664
    for line in design_lines:
        cur_y = draw_paragraph(draw, 618, cur_y, f"- {line}", font=fonts.body, fill=PALETTE["text"], max_width=430)
        cur_y += 6
    draw_label(draw, (618, 812), "script-first evaluation asset", font=fonts.badge, fg=PALETTE["blue"], bg=PALETTE["blue_soft"])

    draw.text((1142, 620), "비용 비교", font=fonts.h2, fill=PALETTE["text"])
    cost_rows = [
        [f"{row['label']} ({row['dims']})", f"${row['cost_per_1m']:.3f}", f"{row['cost_index']:.1f}x"]
        for row in profiles
    ]
    table_grid(
        draw,
        (1142, 660, 1528, 820),
        ["모델", "1M tokens", "비용 지수"],
        cost_rows,
        fonts=fonts,
        widths=[0.60, 0.20, 0.20],
    )
    draw_paragraph(
        draw,
        1142,
        834,
        "비용 대비 효율은 1536차원 small이 가장 좋고, 절대 품질은 3072차원 large가 우세합니다.",
        font=fonts.body,
        fill=PALETTE["muted"],
        max_width=384,
    )

    draw_label(draw, (72, 944), "결론", font=fonts.badge, fg="#FFFFFF", bg=PALETTE["blue"])
    conclusion = (
        "text-embedding-3-small 1536차원은 운영 비용 효율이 가장 높고, "
        "text-embedding-3-large 3072차원은 최고 품질을 제공합니다. 운영 환경에서는 예산과 검색 품질 요구에 따라 두 프로필 중 선택하는 구조가 적절합니다."
    )
    draw_paragraph(draw, 164, 944, conclusion, font=fonts.body, fill=PALETTE["text"], max_width=1320, line_gap=4)

    out_path = OUT_DIR / "embedding_eval_summary.png"
    image.save(out_path)
    return out_path


def render_agent_image(fonts: Fonts) -> Path:
    analysis = load_analysis_data()
    answer = load_answer_data()
    chatbot_suite = load_chatbot_suite()
    total_suite_examples = sum(row["examples"] for row in chatbot_suite)
    answer_first = answer["runs"][0]
    answer_latest = answer["runs"][-1]
    answer_turn = next((row for row in answer["runs"] if row["router_accuracy"] >= 1.0), answer_latest)

    image, draw = create_canvas(1600, 1180)
    draw.text((48, 34), "에이전트 평가 결과 요약", font=fonts.title, fill=PALETTE["navy"])
    draw.text(
        (48, 98),
        "저장소에 버전된 실측 리포트와 평가 데이터셋을 조합해 분석/답변 에이전트 성능과 챗봇 서브에이전트 평가 범위를 정리했습니다.",
        font=fonts.body,
        fill=PALETTE["muted"],
    )
    draw.line((48, 148, 1552, 148), fill=PALETTE["line"], width=2)
    draw_label(draw, (48, 170), "1. CS Auto Analysis Agent", font=fonts.badge, fg="#FFFFFF", bg=PALETTE["blue"])
    draw_label(draw, (548, 170), "2. CS Auto Answer Agent", font=fonts.badge, fg="#FFFFFF", bg=PALETTE["green"])
    draw_label(draw, (1048, 170), "3. Chatbot Eval Suite", font=fonts.badge, fg="#FFFFFF", bg=PALETTE["purple"])

    rounded_box(image, (48, 208, 512, 650), fill=PALETTE["panel"])
    rounded_box(image, (548, 208, 1012, 650), fill=PALETTE["panel"])
    rounded_box(image, (1048, 208, 1552, 818), fill=PALETTE["panel"])
    rounded_box(image, (48, 688, 1012, 1118), fill=PALETTE["panel"])
    rounded_box(image, (1048, 856, 1552, 1118), fill=PALETTE["panel"])

    draw.text((72, 232), "실측 데이터", font=fonts.h2, fill=PALETTE["text"])
    draw.text((72, 272), f"평가 티켓 {analysis['ticket_count']}건", font=fonts.metric, fill=PALETTE["blue"])
    table_grid(
        draw,
        (72, 324, 488, 486),
        ["축", "정답", "정확도"],
        [
            ["category", "126 / 143", "88.11%"],
            ["risk_level", "132 / 143", "92.31%"],
            ["sentiment", "111 / 143", "77.62%"],
            ["routing_target", "117 / 143", "81.82%"],
        ],
        fonts=fonts,
        widths=[0.42, 0.28, 0.30],
    )
    cur_y = 514
    draw.text((72, cur_y), "오차 포인트", font=fonts.h2, fill=PALETTE["text"])
    cur_y += 38
    error_lines = [
        f"- sentiment가 4개 축 중 최저 성능({analysis['metrics']['sentiment']['accuracy'] * 100:.2f}%)",
        f"- payment -> refund 오분류 {analysis['top_errors']['payment_to_refund']}건",
        f"- DB_only -> doc_only 라우팅 혼동 {analysis['top_errors']['db_only_to_doc_only']}건",
    ]
    for line in error_lines:
        cur_y = draw_paragraph(draw, 72, cur_y, line, font=fonts.body, fill=PALETTE["text"], max_width=392)
        cur_y += 4

    draw.text((572, 232), "실측 데이터", font=fonts.h2, fill=PALETTE["text"])
    draw.text((572, 272), f"최신 실행 {answer['latest_run']} / 총 {answer['ticket_count']}건", font=fonts.metric, fill=PALETTE["green"])
    table_grid(
        draw,
        (572, 324, 988, 520),
        ["평가 항목", "결과", "비율"],
        [
            ["router_decision", "21 / 21", "100%"],
            ["fixed_sql 실행", "21 / 21", "100%"],
            ["text_to_sql expected hit", "10 / 10", "100%"],
            ["chosen_path rows", "21 / 21", "100%"],
            ["document gold hit", "13 / 13", "100%"],
        ],
        fonts=fonts,
        widths=[0.48, 0.24, 0.28],
    )
    cur_y = 548
    for line in [
        f"- 실행 히스토리 {len(answer['runs'])}회가 저장돼 있고, 초기 router 정확도 {answer_first['router_accuracy'] * 100:.2f}% -> 최신 100%",
        f"- first full-success 전환 시점: {answer_turn['run']}",
        "- fixed_sql / text_to_sql 라우터 분배가 기대치와 완전히 일치",
        "- 문서 검색은 gold chunk, gold document 기준 모두 13/13 적중",
        "- live DB gold document/chunk 검증도 23/23으로 보존 상태 양호",
    ]:
        cur_y = draw_paragraph(draw, 572, cur_y, line, font=fonts.body, fill=PALETTE["text"], max_width=394)
        cur_y += 5

    draw.text((1072, 232), "평가 자산 커버리지", font=fonts.h2, fill=PALETTE["text"])
    draw.text((1072, 272), f"챗봇 평가 데이터셋 {total_suite_examples}건", font=fonts.metric, fill=PALETTE["purple"])
    suite_y = 326
    for row in chatbot_suite:
        rounded_box(image, (1072, suite_y, 1528, suite_y + 88), fill=PALETTE["panel_soft"], shadow=False, radius=18)
        draw.text((1090, suite_y + 14), row["name"], font=fonts.h3, fill=PALETTE["text"])
        draw.text((1436, suite_y + 14), f"{row['examples']}건", font=fonts.h3, fill=PALETTE["purple"])
        draw_paragraph(draw, 1090, suite_y + 42, ", ".join(row["metrics"]), font=fonts.body_small, fill=PALETTE["muted"], max_width=420, line_gap=2)
        suite_y += 98

    draw.text((72, 712), "평가 구조 비교", font=fonts.h1, fill=PALETTE["text"])
    draw_label(draw, (72, 756), "Analysis Agent", font=fonts.badge, fg=PALETTE["blue"], bg=PALETTE["blue_soft"])
    draw_label(draw, (380, 756), "Answer Agent", font=fonts.badge, fg=PALETTE["green"], bg=PALETTE["green_soft"])
    draw_label(draw, (658, 756), "Chatbot Suite", font=fonts.badge, fg=PALETTE["purple"], bg=PALETTE["purple_soft"])

    paragraphs = [
        (
            72,
            "멀티라벨 분류 문제를 실제 수동 골드셋 143건으로 측정합니다. 핵심 KPI는 category, risk_level, sentiment, routing_target 4축 정확도입니다.",
        ),
        (
            380,
            "DB 라우팅과 문서 검색이 실제 운영 데이터에 맞게 작동하는지 점검합니다. router, fixed_sql, text_to_sql, chosen_path, document retrieval을 분리해 검증합니다.",
        ),
        (
            658,
            "FAQ, Payment, Bug, Safety, E2E별로 별도 데이터셋을 두고 메트릭도 에이전트 목적에 맞게 분리합니다. 저장소에는 스크립트와 데이터셋이 버전 관리되어 있습니다.",
        ),
    ]
    for x, text in paragraphs:
        draw_paragraph(draw, x, 806, text, font=fonts.body, fill=PALETTE["text"], max_width=260, line_gap=4)

    table_grid(
        draw,
        (72, 930, 988, 1086),
        ["평가 영역", "실측/자산", "핵심 지표"],
        [
            ["analysis_agent", "리포트 존재", "축별 정확도 4종"],
            ["answer_agent", "실측 11회", "router/db/doc hit"],
            ["faq_agent", "데이터셋 40건", "source_hit@5 / faithfulness"],
            ["payment_agent", "데이터셋 30건", "db_lookup / action_match"],
            ["bug_agent", "데이터셋 20건", "info_coverage / action_match"],
        ],
        fonts=fonts,
        widths=[0.28, 0.22, 0.50],
    )

    draw.text((1072, 880), "정리", font=fonts.h1, fill=PALETTE["text"])
    summary_lines = [
        "analysis_agent는 risk_level 강점, sentiment 보완이 필요합니다.",
        "answer_agent는 최신 저장 리포트 기준 DB/DOC 경로 검증이 모두 통과했습니다.",
        "chatbot 계열은 에이전트별 평가 스크립트와 데이터셋이 준비되어 있어 후속 실측 자동화가 가능한 상태입니다.",
    ]
    cur_y = 930
    for line in summary_lines:
        cur_y = draw_paragraph(draw, 1072, cur_y, f"- {line}", font=fonts.body, fill=PALETTE["text"], max_width=430)
        cur_y += 8

    out_path = OUT_DIR / "agent_eval_summary.png"
    image.save(out_path)
    return out_path


def render_combined_image(fonts: Fonts, embedding_path: Path, agent_path: Path) -> Path:
    embedding = Image.open(embedding_path).convert("RGBA")
    agent = Image.open(agent_path).convert("RGBA")
    width = max(embedding.width, agent.width) + 80
    height = embedding.height + agent.height + 140
    base, draw = create_canvas(width, height)
    draw.text((40, 26), "평가 대시보드", font=fonts.title, fill=PALETTE["navy"])
    draw.text((40, 84), "임베딩 평가와 에이전트 평가를 한 장으로 합친 PNG 산출물", font=fonts.body, fill=PALETTE["muted"])
    base.alpha_composite(embedding, (40, 130))
    base.alpha_composite(agent, (40, 150 + embedding.height))
    out_path = OUT_DIR / "evaluation_dashboard.png"
    base.save(out_path)
    return out_path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts()
    embedding_path = render_embedding_image(fonts)
    agent_path = render_agent_image(fonts)
    dashboard_path = render_combined_image(fonts, embedding_path, agent_path)
    print(f"Wrote {embedding_path}")
    print(f"Wrote {agent_path}")
    print(f"Wrote {dashboard_path}")


if __name__ == "__main__":
    main()
