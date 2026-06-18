from __future__ import annotations

import json
import re
from pathlib import Path
from html import unescape

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
IS_BUNDLE_SCRIPT = BASE_DIR.name == "scripts" and BASE_DIR.parent.name == "sj_data_preprocessing"
if IS_BUNDLE_SCRIPT:
    BUNDLE_DIR = BASE_DIR.parent
    DATA_DIR = BUNDLE_DIR / "raw_data"
    OUTPUT_PATH = BUNDLE_DIR / "processed_data" / "hoyoverse_term_policy_notice.csv"
else:
    DOCS_DIR = BASE_DIR.parents[1]
    DATA_DIR = DOCS_DIR / "ihy_data-20260615T004221Z-3-001" / "ihy_data"
    OUTPUT_PATH = BASE_DIR / "hoyoverse_term_policy_notice.csv"

REQUIRED_COLUMNS = [
    "documents_id",
    "source_type",
    "category",
    "title",
    "raw_content",
    "source_url",
    "published_at",
    "updated_at",
]

NOISE_LINE_PATTERNS = [
    r"^여행자(?:들)?\s*안녕[~!！.\s]*$",
    r"^여행자님,?\s*안녕(?:하세요)?[~!！.\s]*$",
    r"^안녕,?\s*여행자(?:들)?[~!！.\s]*$",
    r"^난\s*티바트\s*대륙의\s*.*?일상이이야.*$",
    r"^오늘은.+?(?:소개해\s*줄게|소개해\s*줄\s*거야|확인해\s*보자|살펴보자)[~!！.\s]*$",
    r"^그럼\s*(?:같이|함께)\s*(?:확인해\s*보자|살펴보자|알아보자)[~!！.\s]*$",
    r"^같이\s*확인해\s*보자[~!！.\s]*$",
    r"^함께\s*살펴보(?:자|도록\s*할까요)[~!！.\s]*$",
    r"^우리\s*함께.+?(?:알아보자|확인해\s*보자)[~!！.\s]*$",
    r"^.+?에\s*대해\s*알아보자구[~!！.\s]*$",
    r"^목록으로$",
    r"^이전\s*글$",
    r"^다음\s*글$",
    r"^공유하기$",
    r"^댓글\s*\d*$",
    r"^댓글$",
    r"^좋아요\s*\d*$",
    r"^조회\s*\d*$",
    r"^스크랩$",
    r"^카페\s*앱으로\s*보기$",
    r"^작성자\s*정보$",
    r"^전체글\s*보기$",
    r"^본문\s*기타\s*기능$",
    r"^신고하기$",
    r"^인쇄$",
]

NOISE_BLOCK_PATTERNS = [
    r"PlayStation[^\n]+registered trademarks[^\n]*",
    r"\*\s*작품에 등장하는 인물, 제품 및 단체는 실제와 무관한 것으로 허구임을 밝힙니다\.",
]

TEXT_REPLACEMENTS = [
    ("HoYoSketch", "유니Sketch"),
    ("HoYoWiki", "유니Wiki"),
    ("HoYoLAB", "유니LAB"),
    ("HoYoPlay", "유니Play"),
    ("〈원신〉 HoYoverse 통행증", "〈일상〉 유니버스 통행증"),
    ("HoYoverse 통행증", "유니버스 통행증"),
    ("HoYoverse Account", "유니버스 계정"),
    ("HoYoverse 개인정보처리방침", "유니버스 개인정보처리방침"),
    ("HOYO", "유니"),
    ("HoYo", "유니"),
    ("hoyo", "uni"),
    ("miHoYo\\Genshin Impact", "Universe\\Daily"),
    ("miHoYo.GenshinImpact", "Universe.DailyImpact"),
    ("GenshinImpact", "DailyImpact"),
    ("Genshin Impact", "Daily Impact"),
    ("Genshin_cs@mihoyo.com", "support@universe.example"),
    ("genshin_cs@hoyoverse.com", "support@universe.example"),
    ("genshincs_kr@universe.example", "support@universe.example"),
    ("kr_mkt_global@hoyoverse.com", "support@universe.example"),
    ("privacy@hoyoverse.com", "privacy@universe.example"),
    ("genshin.hoyoverse.com", "support.universe.example"),
    ("genshin.mihoyo.com", "support.universe.example"),
    ("account.hoyoverse.com", "account.universe.example"),
    ("cafe.naver.com/genshin", "cafe.naver.com/daily"),
    ("HoYoverse", "유니버스"),
    ("호요버스", "유니버스"),
    ("미호요", "유니버스"),
    ("원신", "일상"),
    ("Genshin", "Daily"),
    ("genshin", "daily"),
    ("miHoYo", "유니버스"),
    ("mihoyo", "universe"),
    ("페이몬", "일상이"),
    ("paimon", "daily"),
    ("Paimon", "Daily"),
    ("???? 통행증", "유니버스 통행증"),
    ("????통행증", "유니버스 통행증"),
    ("???? ???? APP", "유니버스 앱"),
    ("???? ????알림", "유니버스 앱 알림"),
    ("???? ???? 알림", "유니버스 앱 알림"),
    ("???? ???? 이벤트", "유니버스 앱 이벤트"),
    ("???? ???? 정보", "게임 도구 정보"),
    ("???? ????", "유니버스 앱"),
    ("??_cs@universe.example", "support@universe.example"),
    ("@??impact_KR", "@dailyimpact_KR"),
    ("C:\\Users\\xxx\\AppData\\LocalLow\\????\\??", "C:\\Users\\xxx\\AppData\\LocalLow\\Universe\\Daily"),
    ("%USERPROFILE%\\AppData\\LocalLow\\????\\??", "%USERPROFILE%\\AppData\\LocalLow\\Universe\\Daily"),
    ("게임 설치 목록의 ??\\?? Game 파일", "게임 설치 목록의 Universe\\Daily Game 파일"),
    ("> ?? > ?? game > ??Impact.exe", "> Universe > Daily Game > DailyImpact.exe"),
    ("??->?? Game->??Impact.exe", "Universe->Daily Game->DailyImpact.exe"),
    ("??Impact.exe", "DailyImpact.exe"),
    ("?? Game", "Daily Game"),
    ("◇ ????: 물", "◇ 신의 눈: 물"),
    ("◇ ????: 번개", "◇ 신의 눈: 번개"),
    ("◇ ???: 물", "◇ 신의 눈: 물"),
    ("◇ ???: 번개", "◇ 신의 눈: 번개"),
    ("★????: 물", "★신의 눈: 물"),
    ("★????: 번개", "★신의 눈: 번개"),
    ("★ ????: 물", "★ 신의 눈: 물"),
    ("★ ????: 번개", "★ 신의 눈: 번개"),
    ("★???: 물", "★신의 눈: 물"),
    ("★???: 번개", "★신의 눈: 번개"),
    ("★ ???: 물", "★ 신의 눈: 물"),
    ("★ ???: 번개", "★ 신의 눈: 번개"),
    ("운명의 자리: ????", "운명의 자리: 미상"),
    ("운명의 자리: ???", "운명의 자리: 미상"),
    ("ID: hoyoverse PW: paimon", "ID: universe PW: daily"),
    ("ID: hoyoverse", "ID: universe"),
    ("PW: paimon", "PW: daily"),
]

IDENTIFIER_REPLACEMENTS = [
    ("hoyoverse_qna_onlygenshin", "universe_qna_onlydaily"),
    ("hoyoverse_qna_common", "universe_qna_common"),
    ("hoyoverse_policy", "universe_policy"),
    ("hoyoverse_통행증_이슈", "유니버스_통행증_이슈"),
]

OTHER_GAME_TERMS = [
    "붕괴: 스타레일",
    "젠레스 존 제로",
    "붕괴3rd",
    "미해결사건부",
]


def normalize_project_terms(value: object) -> str:
    if pd.isna(value):
        return ""

    text = str(value)
    for source, target in TEXT_REPLACEMENTS:
        text = text.replace(source, target)
    text = re.sub(r"https?://[^\s\"')<>]*hoyoverse[^\s\"')<>]*", "https://support.universe.example", text)
    text = re.sub(r"[\w.+-]+@[\w.-]*(?:hoyoverse|mihoyo|genshin)[\w.-]*", "support@universe.example", text, flags=re.IGNORECASE)
    return text


def normalize_identifier(value: object) -> str:
    text = normalize_project_terms(value)
    for source, target in IDENTIFIER_REPLACEMENTS:
        text = text.replace(source, target)
    return text


def normalize_existing_csv(path: Path) -> None:
    if not path.exists():
        return

    df = pd.read_csv(path).fillna("")
    for column in df.columns:
        if column == "source_type":
            df[column] = df[column].map(normalize_identifier)
        else:
            df[column] = df[column].map(normalize_project_terms)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"normalized existing csv: {path}")


def remove_cross_game_lines(text: str) -> str:
    cleaned_lines: list[str] = []
    replacement_line = "《일상》과 같은 유니버스 제공 게임 제품."

    for raw_line in text.splitlines():
        line = raw_line.strip()
        has_other_game = any(term in line for term in OTHER_GAME_TERMS)
        if not has_other_game:
            cleaned_lines.append(raw_line)
            continue
        if "일상" in line:
            if not cleaned_lines or cleaned_lines[-1] != replacement_line:
                cleaned_lines.append(replacement_line)
            continue
        if re.search(r"https?://|@|고객센터|이메일|메일|게임 제품|제공 게임|목록|,|，|/|ㆍ", line):
            continue
        cleaned_lines.append(raw_line)

    return "\n".join(cleaned_lines)


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"<([^<>]*[가-힣][^<>]*)>", r"「\1」", text)
    return text


def remove_noise_lines(text: str) -> str:
    cleaned_lines: list[str] = []
    seen_lines: set[str] = set()
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            cleaned_lines.append("")
            continue
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in NOISE_LINE_PATTERNS):
            continue
        if line in seen_lines:
            continue
        seen_lines.add(line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""

    text = normalize_project_terms(value)
    text = strip_html(text)
    text = normalize_project_terms(text)
    text = re.sub(r"\[\[\[CONTENT-ELEMENT-\d+\]\]\]", "", text)
    text = text.replace("\ufeff", "").replace("\u200b", "")
    text = text.replace("&#8203;", "")
    text = text.replace("\xa0", " ")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    for pattern in NOISE_BLOCK_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = remove_cross_game_lines(text)
    text = remove_noise_lines(text)
    text = normalize_project_terms(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_datetime(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    parsed = parsed.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    return parsed.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")


def build_naver_documents(path: Path, source_type: str, id_prefix: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"article_id": "string"})
    published_at = normalize_datetime(df["write_datetime"])

    category = df["head_name"].fillna("").astype(str).str.strip()
    category = category.mask(category.eq(""), df["menu_name"].fillna("").astype(str).str.strip())
    document_ids = [f"{id_prefix}-{idx}" for idx in range(1, len(df) + 1)]

    return pd.DataFrame(
        {
            "documents_id": document_ids,
            "source_type": normalize_identifier(source_type),
            "category": category.map(clean_text),
            "title": df["title"].map(clean_text),
            "raw_content": df["content_text"].map(clean_text),
            "source_url": df["pc_url"].fillna("").map(normalize_project_terms).astype(str).str.strip(),
            "published_at": published_at,
            "updated_at": published_at,
        }
    )


def extract_korean_date(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = map(int, match.groups())
            return f"{year:04d}-{month:02d}-{day:02d} 00:00:00"
    return ""


def build_policy_documents() -> pd.DataFrame:
    terms_json = json.loads((DATA_DIR / "hoyoverse_terms_ko.json").read_text(encoding="utf-8-sig"))
    terms_text = clean_text(terms_json.get("content_text", ""))
    terms_date = extract_korean_date(
        terms_text,
        [
            r"시행일자:\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일",
            r"시행일자:\s*(\d{4})년\s*(\d{1,2})월(\d{1,2})일",
        ],
    )

    privacy_text = clean_text((DATA_DIR / "hoyoverse_privacy_ko.txt").read_text(encoding="utf-8"))
    privacy_date = extract_korean_date(
        privacy_text,
        [r"버전 날짜:\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일"],
    )

    return pd.DataFrame(
        [
            {
                "documents_id": "HYV-TER-1",
                "source_type": "universe_policy",
                "category": "terms",
                "title": "일상 이용약관",
                "raw_content": terms_text,
                "source_url": normalize_project_terms(terms_json.get("source_url", "")),
                "published_at": terms_date,
                "updated_at": terms_date,
            },
            {
                "documents_id": "HYV-PRI-1",
                "source_type": "universe_policy",
                "category": "privacy",
                "title": "유니버스 개인정보처리방침",
                "raw_content": privacy_text,
                "source_url": "",
                "published_at": privacy_date,
                "updated_at": privacy_date,
            },
        ]
    )


def main() -> None:
    documents = pd.concat(
        [
            build_naver_documents(
                DATA_DIR / "naver_cafe_notice.csv",
                source_type="naver_cafe_notice",
                id_prefix="NVC-NOT",
            ),
            build_naver_documents(
                DATA_DIR / "naver_cafe_guides.csv",
                source_type="naver_cafe_guide",
                id_prefix="NVC-GDE",
            ),
            build_policy_documents(),
        ],
        ignore_index=True,
    )

    documents = documents[REQUIRED_COLUMNS]
    excluded_categories = {"신규 무기"}
    excluded_rows = documents["category"].astype(str).str.strip().isin(excluded_categories)
    if excluded_rows.any():
        print(f"drop excluded category rows: {int(excluded_rows.sum())}")
        documents = documents.loc[~excluded_rows].reset_index(drop=True)
    voice_actor_rows = documents["category"].astype(str).str.strip().eq("성우 공개")
    if voice_actor_rows.any():
        print(f"drop voice actor category rows: {int(voice_actor_rows.sum())}")
        documents = documents.loc[~voice_actor_rows].reset_index(drop=True)

    duplicated_ids = documents["documents_id"].duplicated()
    if duplicated_ids.any():
        duplicates = documents.loc[duplicated_ids, "documents_id"].tolist()
        raise ValueError(f"documents_id duplicates found: {duplicates[:10]}")

    empty_content = documents["raw_content"].eq("")
    if empty_content.any():
        empty_ids = documents.loc[empty_content, "documents_id"].tolist()
        print(f"drop empty raw_content rows: {len(empty_ids)} {empty_ids[:10]}")
        documents = documents.loc[~empty_content].reset_index(drop=True)

    documents.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    print(f"saved: {OUTPUT_PATH}")
    print(f"rows: {len(documents)}")
    print(documents["source_type"].value_counts().to_string())


if __name__ == "__main__":
    main()


