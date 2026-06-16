from __future__ import annotations

import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
COMBINED_PATH = BASE_DIR / "analysis_eval_all_axes_10_each_20260616.csv"

OVERRIDES: dict[str, dict[str, str]] = {
    "1": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "2": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "10": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "12": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "positive", "gold_routing_target": "doc_only"},
    "13": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "14": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "17": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "20": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "23": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "24": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "25": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "120": {"gold_category": "policy", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "123": {"gold_category": "policy", "gold_risk_level": "HIGH", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "640": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "positive", "gold_routing_target": "doc_only"},
    "731": {"gold_category": "account", "gold_risk_level": "MID", "gold_sentiment": "negative", "gold_routing_target": "DB_only"},
    "776": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "788": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "fixed_answer"},
    "1150": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "1160": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "1164": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "1209": {"gold_category": "account", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB_only"},
    "1367": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "positive", "gold_routing_target": "doc_only"},
    "1524": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "1676": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "1683": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "positive", "gold_routing_target": "doc_only"},
    "1795": {"gold_category": "payment", "gold_risk_level": "MID", "gold_sentiment": "neutral", "gold_routing_target": "DB_only"},
    "1911": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "fixed_answer"},
    "2229": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "2353": {"gold_category": "refund", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB&DOC"},
    "2668": {"gold_category": "gacha", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "DB_only"},
    "2936": {"gold_category": "account", "gold_risk_level": "HIGH", "gold_sentiment": "neutral", "gold_routing_target": "DB_only"},
    "3117": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "3143": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "3440": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "3463": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "4201": {"gold_category": "account", "gold_risk_level": "HIGH", "gold_sentiment": "neutral", "gold_routing_target": "DB_only"},
    "4267": {"gold_category": "policy", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB&DOC"},
    "4453": {"gold_category": "policy", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "4469": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "4567": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "4710": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "4808": {"gold_category": "gacha", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "DB_only"},
    "4821": {"gold_category": "policy", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "4904": {"gold_category": "payment", "gold_risk_level": "HIGH", "gold_sentiment": "neutral", "gold_routing_target": "DB_only"},
    "5045": {"gold_category": "policy", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "5127": {"gold_category": "gacha", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB&DOC"},
    "5137": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "5292": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "fixed_answer"},
    "5595": {"gold_category": "account", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB_only"},
    "5694": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "6020": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "6074": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "6611": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "6682": {"gold_category": "account", "gold_risk_level": "MID", "gold_sentiment": "negative", "gold_routing_target": "DB_only"},
    "6683": {"gold_category": "policy", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB&DOC"},
    "6686": {"gold_category": "policy", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB&DOC"},
    "6771": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "6780": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "negative", "gold_routing_target": "doc_only"},
    "6978": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "7113": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "7174": {"gold_category": "policy", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB&DOC"},
    "7298": {"gold_category": "account", "gold_risk_level": "MID", "gold_sentiment": "negative", "gold_routing_target": "DB_only"},
    "7300": {"gold_category": "account", "gold_risk_level": "MID", "gold_sentiment": "negative", "gold_routing_target": "DB_only"},
    "7502": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "7560": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "7768": {"gold_category": "refund", "gold_risk_level": "MID", "gold_sentiment": "neutral", "gold_routing_target": "DB&DOC"},
    "8005": {"gold_category": "policy", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "8268": {"gold_category": "policy", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
    "8424": {"gold_category": "gacha", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "DB_only"},
    "8533": {"gold_category": "general", "gold_risk_level": "LOW", "gold_sentiment": "positive", "gold_routing_target": "DB_only"},
    "8547": {"gold_category": "payment", "gold_risk_level": "HIGH", "gold_sentiment": "negative", "gold_routing_target": "DB&DOC"},
    "8829": {"gold_category": "gacha", "gold_risk_level": "HIGH", "gold_sentiment": "neutral", "gold_routing_target": "DB&DOC"},
    "9022": {"gold_category": "bug", "gold_risk_level": "LOW", "gold_sentiment": "neutral", "gold_routing_target": "doc_only"},
}

DERIVED_FILES = {
    "category": BASE_DIR / "analysis_eval_category_10_each_20260616.csv",
    "risk": BASE_DIR / "analysis_eval_risk_10_each_20260616.csv",
    "sentiment": BASE_DIR / "analysis_eval_sentiment_10_each_20260616.csv",
    "routing": BASE_DIR / "analysis_eval_routing_10_each_20260616.csv",
}


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = list(csv.DictReader(COMBINED_PATH.open(encoding="utf-8-sig")))
    fieldnames = list(rows[0].keys())

    for row in rows:
        override = OVERRIDES.get(row["ticket_id"])
        if override:
            row.update(override)
        row["review_status"] = "manual_checked"

    write_csv(COMBINED_PATH, rows, fieldnames)

    for axis, path in DERIVED_FILES.items():
        axis_rows = [row for row in rows if row["focus_axis"] == axis]
        write_csv(path, axis_rows, fieldnames)

    print(f"updated combined rows: {len(rows)}")
    print(f"ticket_id overrides registered: {len(OVERRIDES)}")


if __name__ == "__main__":
    main()
