from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd

from make_ihy_documents_csv import normalize_identifier, normalize_project_terms


BASE_DIR = Path(__file__).resolve().parent
IS_BUNDLE_SCRIPT = BASE_DIR.name == "scripts" and BASE_DIR.parent.name == "sj_data_preprocessing"
if IS_BUNDLE_SCRIPT:
    BUNDLE_DIR = BASE_DIR.parent
    FAQ_PATH = BUNDLE_DIR / "raw_data" / "hoyoverse_qna_cleaned.csv"
    TERM_POLICY_NOTICE_PATH = BUNDLE_DIR / "processed_data" / "hoyoverse_term_policy_notice.csv"
    FAQ_OUTPUT_PATH = BUNDLE_DIR / "processed_data" / "hoyoverse_qna_chunked.csv"
    TERM_POLICY_NOTICE_OUTPUT_PATH = BUNDLE_DIR / "processed_data" / "hoyoverse_term_policy_notice_chunked.csv"
else:
    DOCS_DIR = BASE_DIR.parents[1]
    FAQ_PATH = DOCS_DIR / "data_faq-20260615T004218Z-3-001" / "data_faq" / "hoyoverse_qna_cleaned.csv"
    TERM_POLICY_NOTICE_PATH = BASE_DIR / "hoyoverse_term_policy_notice.csv"
    FAQ_OUTPUT_PATH = FAQ_PATH.with_name("hoyoverse_qna_chunked.csv")
    TERM_POLICY_NOTICE_OUTPUT_PATH = TERM_POLICY_NOTICE_PATH.with_name("hoyoverse_term_policy_notice_chunked.csv")

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
MAX_CHARS = 2200
MIN_CHARS_TO_SPLIT = 900
MIN_CHARS_TO_KEEP = 80
MIN_CHARS_TO_ENRICH = 160


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = normalize_project_terms(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return normalize_project_terms(text).strip()


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", normalize_text(text)).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def split_by_policy_article(text: str) -> list[tuple[str, str]]:
    lines = normalize_text(text).splitlines()
    chunks: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        is_article = bool(re.match(r"^제\s*\d+\s*조(?:\s|\(|$)", stripped))
        if is_article and current_lines:
            chunks.append((current_title or stripped, current_lines))
            current_lines = []
        if is_article:
            current_title = stripped
        current_lines.append(line)

    if current_lines:
        chunks.append((current_title or "정책 조항", current_lines))

    if len(chunks) <= 1:
        return []
    return [(title, "\n".join(lines).strip()) for title, lines in chunks]


def split_by_notice_sections(text: str) -> list[tuple[str, str]]:
    lines = normalize_text(text).splitlines()
    chunks: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []

    heading_pattern = re.compile(
        r"^(={3,}.+={3,}|[◆●■▶]\s*.+|(?:이벤트|점검|업데이트|보상|참여|기간|주의|안내|수정|발견한 문제).{0,40}$)"
    )

    for line in lines:
        stripped = line.strip()
        is_heading = bool(heading_pattern.match(stripped))
        if is_heading and current_lines and len("\n".join(current_lines)) >= MIN_CHARS_TO_SPLIT:
            chunks.append((current_title or stripped, current_lines))
            current_lines = []
        if is_heading:
            current_title = stripped.strip("= ").strip() or current_title
        current_lines.append(line)

    if current_lines:
        chunks.append((current_title or "본문", current_lines))

    if len(chunks) <= 1:
        return []
    return [(title, "\n".join(lines).strip()) for title, lines in chunks]


def split_by_paragraph_budget(text: str, max_chars: int = MAX_CHARS) -> list[tuple[str, str]]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalize_text(text)) if part.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if not current:
            current = paragraph
            continue
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}"
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)

    expanded: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            expanded.append(chunk)
            continue
        sentences = re.split(r"(?:(?<=[.!?。])|(?<=다\.)|(?<=요\.)|(?<=니다\.))\s+", chunk)
        current = ""
        for sentence in sentences:
            if not sentence:
                continue
            if current and len(current) + len(sentence) + 1 > max_chars:
                expanded.append(current.strip())
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            expanded.append(current.strip())

    hard_wrapped: list[str] = []
    for chunk in expanded:
        if len(chunk) <= max_chars:
            hard_wrapped.append(chunk)
            continue
        hard_wrapped.extend(wrap_long_text(chunk, max_chars=max_chars))

    return [(first_line(chunk), chunk) for chunk in hard_wrapped]


def wrap_long_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    text = normalize_text(text)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = max(text.rfind("\n", start, end), text.rfind(" ", start, end))
            if split_at > start + max_chars // 2:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


def first_line(text: str) -> str:
    for line in normalize_text(text).splitlines():
        if line.strip():
            return line.strip()[:80]
    return "본문"


def build_search_text(row: pd.Series, content: str) -> str:
    title = normalize_text(row["title"])
    category = normalize_text(row["category"])
    content = normalize_text(content)

    if len(content) >= MIN_CHARS_TO_ENRICH:
        return content

    parts = [
        f"제목: {title}",
        f"분류: {category}",
    ]
    if content:
        parts.append(f"내용: {content}")
    return "\n".join(parts)


def split_document(row: pd.Series) -> list[tuple[str, str]]:
    text = normalize_text(row["raw_content"])
    source_type = str(row["source_type"])

    if len(text) <= MAX_CHARS:
        return [(str(row["title"]), text)]

    if source_type == "universe_policy":
        policy_chunks = split_by_policy_article(text)
        if policy_chunks:
            return flatten_large_chunks(policy_chunks)

    section_chunks = split_by_notice_sections(text)
    if section_chunks:
        return flatten_large_chunks(section_chunks)

    return split_by_paragraph_budget(text)


def flatten_large_chunks(chunks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    flattened: list[tuple[str, str]] = []
    for title, content in chunks:
        if len(content) <= MAX_CHARS:
            flattened.append((title, content))
            continue
        sub_chunks = split_by_paragraph_budget(content)
        for index, (_, sub_content) in enumerate(sub_chunks, start=1):
            suffix = f" {index}" if len(sub_chunks) > 1 else ""
            flattened.append((f"{title}{suffix}", sub_content))
    return flattened


def build_faq_chunks() -> pd.DataFrame:
    df = pd.read_csv(FAQ_PATH).fillna("")
    for column in ["source_type", "category", "title", "raw_content", "source_url"]:
        if column in df.columns:
            if column == "source_type":
                df[column] = df[column].map(normalize_identifier)
            else:
                df[column] = df[column].map(normalize_text)
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        question = normalize_text(row["title"])
        answer = normalize_text(row["raw_content"])
        answer_chunks = [answer]
        if len(f"질문: {question}\n\n답변:\n{answer}") > MAX_CHARS:
            answer_chunks = [chunk for _, chunk in split_by_paragraph_budget(answer)]

        for index, answer_chunk in enumerate(answer_chunks, start=1):
            documents_id = row["documents_id"]
            title = question
            if len(answer_chunks) > 1:
                documents_id = f"{documents_id}-C{index:03d}"
                title = f"{question} ({index}/{len(answer_chunks)})"
            base_row = {
                "documents_id": documents_id,
                "source_type": row["source_type"],
                "category": row["category"],
                "title": title,
                "raw_content": f"질문: {question}\n\n답변:\n{answer_chunk}",
                "source_url": row["source_url"],
                "published_at": row["published_at"],
                "updated_at": row["updated_at"],
            }
            rows.append(base_row)
    return dedupe_documents(pd.DataFrame(rows, columns=REQUIRED_COLUMNS))


def build_term_policy_notice_chunks() -> pd.DataFrame:
    df = pd.read_csv(TERM_POLICY_NOTICE_PATH).fillna("")
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        chunks = [
            (chunk_title, chunk_text)
            for chunk_title, chunk_text in split_document(row)
            if len(build_search_text(row, chunk_text)) >= MIN_CHARS_TO_KEEP
        ]
        if not chunks:
            chunks = [(str(row["title"]), normalize_text(row["raw_content"]))]
        for index, (chunk_title, chunk_text) in enumerate(chunks, start=1):
            title = normalize_text(row["title"])
            if chunk_title and chunk_title != title:
                title = f"{title} - {chunk_title}"
            base_row = {
                "documents_id": f"{row['documents_id']}-C{index:03d}",
                "source_type": row["source_type"],
                "category": row["category"],
                "title": title[:500],
                "raw_content": build_search_text(row, chunk_text),
                "source_url": row["source_url"],
                "published_at": row["published_at"],
                "updated_at": row["updated_at"],
            }
            rows.append(base_row)
    return dedupe_documents(pd.DataFrame(rows, columns=REQUIRED_COLUMNS))


def dedupe_documents(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.assign(_content_hash=df["title"].astype(str).str.cat(df["raw_content"].astype(str), sep="\n").map(content_hash))
    df = df.drop_duplicates(subset=["_content_hash"], keep="first").copy()
    df = df.drop_duplicates(subset=["source_url", "title", "raw_content"], keep="first").copy()
    df = df.drop(columns=["_content_hash"])
    removed = before - len(df)
    if removed:
        print(f"dedupe removed: {removed}")
    return df.reset_index(drop=True)


def validate(df: pd.DataFrame, name: str) -> None:
    duplicated = df["documents_id"].duplicated()
    if duplicated.any():
        raise ValueError(f"{name}: duplicated documents_id: {df.loc[duplicated, 'documents_id'].head().tolist()}")
    empty = df["raw_content"].fillna("").astype(str).str.strip().eq("")
    if empty.any():
        raise ValueError(f"{name}: empty raw_content: {df.loc[empty, 'documents_id'].head().tolist()}")


def main() -> None:
    faq_chunks = build_faq_chunks()
    validate(faq_chunks, "faq_chunks")
    faq_chunks.to_csv(FAQ_OUTPUT_PATH, index=False, encoding="utf-8")

    term_policy_notice_chunks = build_term_policy_notice_chunks()
    validate(term_policy_notice_chunks, "term_policy_notice_chunks")
    term_policy_notice_chunks.to_csv(TERM_POLICY_NOTICE_OUTPUT_PATH, index=False, encoding="utf-8")

    print(f"saved: {FAQ_OUTPUT_PATH}")
    print(f"faq rows: {len(faq_chunks)}")
    print(f"saved: {TERM_POLICY_NOTICE_OUTPUT_PATH}")
    print(f"term/policy/notice original rows: {len(pd.read_csv(TERM_POLICY_NOTICE_PATH))}")
    print(f"term/policy/notice chunk rows: {len(term_policy_notice_chunks)}")
    print(term_policy_notice_chunks["source_type"].value_counts().to_string())


if __name__ == "__main__":
    main()

