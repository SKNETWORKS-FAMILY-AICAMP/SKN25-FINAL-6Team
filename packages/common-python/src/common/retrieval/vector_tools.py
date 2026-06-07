from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from typing import Any

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from common.db.connection import db_connection
from common.observability.logger import EVENT_TOOL_COMPLETED, EVENT_TOOL_STARTED, log_event


FAQ_SOURCE_TYPES = (
    "hoyoverse_qna_onlygenshin",
    "hoyoverse_qna_common",
    "hoyoverse_policy",
    "naver_cafe_guide",
    "naver_cafe_notice",
)

SOURCE_PRIORITY = {
    "hoyoverse_qna_common": 5,
    "hoyoverse_qna_onlygenshin": 5,
    "hoyoverse_policy": 4,
    "naver_cafe_guide": 3,
    "naver_cafe_notice": 1,
}

class RetrievalQuery(BaseModel):
    """Normalized retrieval-query enrichment output."""

    query_text: str = Field(description="Compact query used for embeddings and keyword matching")
    preferred_source_types: list[str] = Field(
        default_factory=list,
        description="Preferred documents.source_type values for retrieval",
    )
    preferred_categories: list[str] = Field(
        default_factory=list,
        description="Preferred documents.category values for retrieval",
    )


class RerankResult(BaseModel):
    """Ordered chunk ids selected by the reranker."""

    ordered_chunk_ids: list[str] = Field(description="Most relevant chunk_ids in descending relevance order")


def _embedding_model_name() -> str:
    """Resolve EMBEDDING_MODEL, supporting openai:<model> shorthand."""
    raw = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    return raw.split(":", 1)[1] if raw.startswith("openai:") else raw


def _db_side_vector_search_enabled() -> bool:
    return os.environ.get("RETRIEVAL_DB_SIDE_VECTOR", "true").strip().lower() not in {"0", "false", "no", "off"}


def _cosine(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between query and document embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x**2 for x in a))
    mag_b = math.sqrt(sum(x**2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _tokenize(text: str) -> list[str]:
    """Extract coarse Korean/alphanumeric tokens for lightweight BM25 scoring."""
    return [
        token.lower()
        for token in re.findall(r"[0-9A-Za-z\uac00-\ud7a3_]+", text)
        if len(token.strip()) > 1
    ]


def refine_query_text(text: str, max_terms: int = 16) -> str:
    """Normalize whitespace and deduplicate tokens for retrieval queries."""
    normalized = " ".join(text.strip().split())
    if not normalized:
        return ""

    tokens = _tokenize(normalized)
    if not tokens:
        return normalized[:200]

    deduped = list(dict.fromkeys(tokens))
    return " ".join(deduped[:max_terms])


def _query_patterns(query: str, max_tokens: int = 8) -> list[str]:
    """Generate LIKE patterns used for title/category prefiltering."""
    tokens = list(dict.fromkeys(_tokenize(refine_query_text(query))))
    return [f"%{token}%" for token in tokens[:max_tokens]]


_RULE_POLICY_KEYWORDS = frozenset(["개인정보", "처리방침", "이용약관", "약관"])


def _rule_source_types(text: str) -> list[str]:
    """Return source_type preferences by keyword rules.

    Policy queries are narrowed to hoyoverse_policy; everything else uses all
    FAQ source types so that naver_cafe_guide / naver_cafe_notice docs are
    never excluded by an overly specific LLM enrichment guess.
    """
    if any(kw in text for kw in _RULE_POLICY_KEYWORDS):
        return ["hoyoverse_policy"]
    return list(FAQ_SOURCE_TYPES)


def _fallback_enrich_query(text: str) -> RetrievalQuery:
    """Fallback enrichment when the LLM enrichment step is unavailable."""
    query_text = refine_query_text(text)
    return RetrievalQuery(
        query_text=query_text,
        preferred_source_types=_rule_source_types(text),
        preferred_categories=[],
    )


def enrich_retrieval_query(text: str) -> RetrievalQuery:
    """Use the LLM to normalize retrieval intent; source types are rule-determined."""
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("QUERY_ENRICHMENT_MODEL") or os.environ.get("LLM_MODEL")
    if not api_key or not model:
        return _fallback_enrich_query(text)

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0,
            timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
        ).with_structured_output(RetrievalQuery)
        result = llm.invoke(
            [
                (
                    "system",
                    "You enrich Korean game CS FAQ/RAG search queries. "
                    "Extract a concise Korean query_text and optional category hints. "
                    "Normalize slang, typos, and equivalent phrases into the same canonical Korean FAQ search query. "
                    "For example, similar phrasings about resetting game progress should become one canonical query. "
                    "Do not preserve vague slang when a clearer FAQ title-style query is possible. "
                    "Do not answer the user.",
                ),
                ("user", text),
            ]
        )
        query_text = refine_query_text(result.query_text or text)
        return RetrievalQuery(
            query_text=query_text,
            preferred_source_types=_rule_source_types(text),
            preferred_categories=list(dict.fromkeys(result.preferred_categories))[:8],
        )
    except Exception:
        return _fallback_enrich_query(text)


def _bm25_scores(query: str, rows: list[dict[str, Any]]) -> dict[Any, float]:
    """Score candidate chunks in memory with a simple BM25-like formula."""
    query_terms = _tokenize(query)
    if not query_terms or not rows:
        return {row["chunk_id"]: 0.0 for row in rows}

    tokenized_docs: dict[Any, list[str]] = {}
    document_frequency: Counter[str] = Counter()
    for row in rows:
        text = f"{row.get('title') or ''} {row.get('category') or ''} {row.get('chunk_text') or ''}"
        tokens = _tokenize(text)
        tokenized_docs[row["chunk_id"]] = tokens
        document_frequency.update(set(tokens))

    avg_doc_len = sum(len(tokens) for tokens in tokenized_docs.values()) / max(len(rows), 1)
    k1 = float(os.environ.get("BM25_K1", "1.5"))
    b = float(os.environ.get("BM25_B", "0.75"))
    total_docs = len(rows)
    scores: dict[Any, float] = {}

    for row in rows:
        chunk_id = row["chunk_id"]
        tokens = tokenized_docs[chunk_id]
        term_counts = Counter(tokens)
        doc_len = len(tokens) or 1
        score = 0.0
        for term in query_terms:
            tf = term_counts.get(term, 0)
            if tf == 0:
                continue
            df = document_frequency.get(term, 0)
            idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (1 - b + b * doc_len / max(avg_doc_len, 1))
            score += idf * (tf * (k1 + 1)) / denominator
        scores[chunk_id] = score

    return scores


def _token_matches(query_token: str, document_token: str) -> bool:
    if query_token == document_token:
        return True
    if len(query_token) <= 1 or len(document_token) <= 1:
        return False
    return query_token in document_token or document_token in query_token


def _overlap_ratio(query_terms: set[str], text: str) -> float:
    if not query_terms:
        return 0.0
    document_terms = set(_tokenize(text))
    if not document_terms:
        return 0.0

    matched = 0
    for query_term in query_terms:
        if any(_token_matches(query_term, document_term) for document_term in document_terms):
            matched += 1
    return matched / len(query_terms)


def _field_match_boost(query: str, chunk: dict[str, Any]) -> float:
    query_terms = set(_tokenize(query))
    if not query_terms:
        return 0.0

    title_weight = float(os.environ.get("RETRIEVAL_TITLE_MATCH_WEIGHT", "0.04"))
    category_weight = float(os.environ.get("RETRIEVAL_CATEGORY_MATCH_WEIGHT", "0.01"))
    text_weight = float(os.environ.get("RETRIEVAL_TEXT_MATCH_WEIGHT", "0.006"))

    title_score = _overlap_ratio(query_terms, str(chunk.get("title") or ""))
    category_score = _overlap_ratio(query_terms, str(chunk.get("category") or ""))
    text_score = _overlap_ratio(query_terms, str(chunk.get("chunk_text") or ""))

    return title_score * title_weight + category_score * category_weight + text_score * text_weight


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _truncate_for_rerank(text: str, max_chars: int = 700) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:max_chars]


def _fallback_rerank(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reranked = []
    for index, document in enumerate(documents, start=1):
        result = dict(document)
        result["rerank_rank"] = index
        result["rerank_method"] = "hybrid_pass_through"
        reranked.append(result)
    return reranked


def _llm_rerank_documents(documents: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("RERANKER_MODEL") or os.environ.get("LLM_MODEL")
    if not api_key or not model:
        return _fallback_rerank(documents)

    from langchain_openai import ChatOpenAI

    candidates = []
    for document in documents:
        candidates.append(
            {
                "chunk_id": str(document.get("chunk_id") or ""),
                "title": document.get("title") or "",
                "category": document.get("category") or "",
                "source_type": document.get("source_type") or "",
                "content": _truncate_for_rerank(str(document.get("chunk_text") or "")),
            }
        )

    reranker = ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    ).with_structured_output(RerankResult)

    result = reranker.invoke(
        [
            (
                "system",
                "You rerank Korean game customer-support FAQ evidence. "
                "Order chunk_ids by direct usefulness for answering the user's exact question. "
                "Prefer documents whose title and content explicitly answer the requested topic. "
                "Demote adjacent but different topics, notices, incidents, and partial keyword matches. "
                "Return only the structured ordered_chunk_ids field.",
            ),
            (
                "user",
                json.dumps({"question": query, "candidates": candidates}, ensure_ascii=False),
            ),
        ]
    )

    by_id = {str(document.get("chunk_id") or ""): document for document in documents}
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for chunk_id in result.ordered_chunk_ids:
        chunk_id = str(chunk_id)
        document = by_id.get(chunk_id)
        if document is None or chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(document)

    for document in documents:
        chunk_id = str(document.get("chunk_id") or "")
        if chunk_id not in seen:
            ordered.append(document)

    reranked = []
    for index, document in enumerate(ordered, start=1):
        result_doc = dict(document)
        result_doc["rerank_rank"] = index
        result_doc["rerank_method"] = "llm"
        reranked.append(result_doc)
    return reranked


def _rrf_fuse(
    cosine_ranked: list[tuple[float, dict[str, Any]]],
    bm25_ranked: list[tuple[float, dict[str, Any]]],
    query_text: str,
    k: int = 60,
) -> list[tuple[float, dict[str, Any]]]:
    """Fuse cosine and BM25 rankings with reciprocal-rank fusion."""
    chunk_by_id = {c["chunk_id"]: c for _, c in cosine_ranked + bm25_ranked}
    cosine_rank = {c["chunk_id"]: i for i, (_, c) in enumerate(cosine_ranked)}
    bm25_rank = {c["chunk_id"]: i for i, (_, c) in enumerate(bm25_ranked)}
    fused = []
    for cid in set(cosine_rank) | set(bm25_rank):
        chunk = chunk_by_id[cid]
        source_boost = SOURCE_PRIORITY.get(str(chunk.get("source_type") or ""), 0) * float(
            os.environ.get("RETRIEVAL_SOURCE_PRIORITY_WEIGHT", "0.003")
        )
        field_boost = _field_match_boost(query_text, chunk)
        rrf = (
            1 / (k + cosine_rank.get(cid, len(cosine_rank)) + 1)
            + 1 / (k + bm25_rank.get(cid, len(bm25_rank)) + 1)
            + source_boost
            + field_boost
        )
        chunk["field_match_score"] = field_boost
        fused.append((rrf, chunk_by_id[cid]))
    fused.sort(key=lambda x: x[0], reverse=True)
    return fused


def hybrid_rank_documents(
    *,
    query_vector: list[float],
    query_text: str,
    rows: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Rank document rows with cosine, BM25, and RRF fusion."""
    retrieval_query = refine_query_text(query_text)
    bm25_by_id = _bm25_scores(retrieval_query, rows)

    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        row = dict(row)
        if "cosine_score" in row and row["cosine_score"] is not None:
            # pre-computed by DB via pgvector <=> — skip Python cosine
            cosine_score = float(row["cosine_score"])
            row.pop("embedding_vector", None)
        else:
            raw_vector = str(row.pop("embedding_vector", "")).strip("[]")
            db_vector = [float(value) for value in raw_vector.split(",") if value.strip()]
            cosine_score = _cosine(query_vector, db_vector) if db_vector else 0.0
        bm25_score = bm25_by_id.get(row["chunk_id"], 0.0)
        row["cosine_score"] = cosine_score
        row["bm25_score"] = bm25_score
        row["retrieval_query"] = retrieval_query
        enriched_rows.append(row)

    cosine_ranked = sorted(
        ((row["cosine_score"], row) for row in enriched_rows),
        key=lambda item: item[0],
        reverse=True,
    )
    bm25_ranked = sorted(
        ((row["bm25_score"], row) for row in enriched_rows),
        key=lambda item: item[0],
        reverse=True,
    )
    fused = _rrf_fuse(cosine_ranked, bm25_ranked, retrieval_query)

    results = []
    for fused_score, row in fused[:top_k]:
        result = dict(row)
        result["score"] = round(fused_score, 6)
        result["cosine_score"] = round(float(result["cosine_score"]), 6)
        result["bm25_score"] = round(float(result["bm25_score"]), 6)
        result["field_match_score"] = round(float(result.get("field_match_score", 0.0)), 6)
        results.append(result)
    return results


def _faq_filter_clause() -> tuple[str, list[str]]:
    """Build the FAQ source-type filter clause."""
    source_placeholders = ", ".join(["%s"] * len(FAQ_SOURCE_TYPES))
    params: list[str] = list(FAQ_SOURCE_TYPES)
    return f"d.source_type IN ({source_placeholders})", params


def _enrichment_filter_clause(enrichment: RetrievalQuery | None) -> tuple[str, list[Any]]:
    """Convert enrichment preferences into optional SQL filters."""
    if enrichment is None:
        return "", []

    checks: list[str] = []
    params: list[Any] = []

    source_types = [source for source in enrichment.preferred_source_types if source in FAQ_SOURCE_TYPES]
    if source_types:
        checks.append(f"d.source_type IN ({', '.join(['%s'] * len(source_types))})")
        params.extend(source_types)

    categories = [category for category in enrichment.preferred_categories if category]
    if categories:
        checks.append("d.category = ANY(%s)")
        params.append(categories)

    if not checks:
        return "", []
    return f"AND ({' OR '.join(checks)})", params


def _fetch_candidate_rows(
    *,
    retrieval_query: str,
    candidate_limit: int,
    faq_only: bool,
    enrichment: RetrievalQuery | None = None,
    use_query_filter: bool = True,
    query_vector: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Fetch candidate document chunks from Postgres.

    When query_vector is provided, vector similarity is computed inside the DB
    using pgvector's <=> operator and only the top candidate_limit rows by
    cosine distance are returned — avoiding transferring raw embedding vectors
    over the network. Without query_vector the legacy path returns raw vectors
    for Python-side cosine scoring.
    """
    faq_clause = ""
    faq_params: list[str] = []
    if faq_only:
        clause, faq_params = _faq_filter_clause()
        faq_clause = f"AND {clause}"

    enrichment_clause, enrichment_params = _enrichment_filter_clause(enrichment)

    token_patterns = _query_patterns(retrieval_query)
    if not token_patterns:
        token_patterns = [f"%{retrieval_query}%"]

    text_clause = "TRUE"
    text_params: list[Any] = []
    if use_query_filter:
        text_clause = """
                    (
                        %s = ''
                        OR to_tsvector('simple', c.chunk_text) @@ plainto_tsquery('simple', %s)
                        OR d.title ILIKE %s
                        OR d.category ILIKE %s
                        OR d.title ILIKE ANY(%s)
                        OR d.category ILIKE ANY(%s)
                    )
        """
        text_params = [
            retrieval_query,
            retrieval_query,
            f"%{retrieval_query}%",
            f"%{retrieval_query}%",
            token_patterns,
            token_patterns,
        ]

    source_priority_sql = "CASE " + " ".join(
        f"WHEN d.source_type = '{source_type}' THEN {priority}"
        for source_type, priority in SOURCE_PRIORITY.items()
    ) + " ELSE 0 END"

    if query_vector is not None:
        vector_literal = "[" + ",".join(str(v) for v in query_vector) + "]"
        order_clause = f"e.embedding_vector <=> '{vector_literal}'::vector"
        cosine_select = f"1 - (e.embedding_vector <=> '{vector_literal}'::vector) AS cosine_score"
        embedding_select = ""
    else:
        order_clause = "c.created_at DESC NULLS LAST"
        if not use_query_filter and faq_only:
            order_clause = f"{source_priority_sql} DESC, c.created_at DESC NULLS LAST"
        cosine_select = ""
        embedding_select = "e.embedding_vector::text AS embedding_vector,"

    extra_select = ", ".join(filter(None, [cosine_select]))
    if extra_select:
        extra_select = ", " + extra_select

    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                    c.chunk_id,
                    c.document_id,
                    d.source_type,
                    d.category,
                    d.title,
                    c.chunk_text,
                    {embedding_select}
                    c.created_at
                    {extra_select}
                FROM documents_chunks c
                JOIN documents d ON d.documents_id = c.document_id
                JOIN documents_embeddings e ON e.chunk_id = c.chunk_id
                WHERE
                    {text_clause}
                    {faq_clause}
                    {enrichment_clause}
                ORDER BY {order_clause}
                LIMIT %s
                """,
                (
                    *text_params,
                    *faq_params,
                    *enrichment_params,
                    candidate_limit,
                ),
            )
            return [dict(row) for row in cur.fetchall()]


def search_document_chunks(
    *,
    embedding_json: str,
    query_text: str = "",
    top_k: int | None = None,
    prefer_faq: bool = True,
    enrichment: RetrievalQuery | dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search FAQ-first and broaden the candidate scope if recall is too low."""
    k = top_k or int(os.environ.get("RETRIEVAL_TOP_K", "3"))
    candidate_limit = int(os.environ.get("RETRIEVAL_CANDIDATE_LIMIT", "300"))
    broad_candidate_limit = int(os.environ.get("RETRIEVAL_BROAD_CANDIDATE_LIMIT", "2000"))
    min_candidate_count = int(os.environ.get("RETRIEVAL_MIN_CANDIDATES", "50"))
    query_vec: list[float] = json.loads(embedding_json)
    retrieval_query = refine_query_text(query_text)
    if isinstance(enrichment, dict):
        enrichment = RetrievalQuery.model_validate(enrichment)
    db_side_query_vec = query_vec if _db_side_vector_search_enabled() else None

    rows = _fetch_candidate_rows(
        retrieval_query=retrieval_query,
        candidate_limit=candidate_limit,
        faq_only=prefer_faq,
        enrichment=enrichment,
        use_query_filter=True,
        query_vector=db_side_query_vec,
    )
    candidate_scope = "faq"

    if prefer_faq and len(rows) < min_candidate_count:
        broad_rows = _fetch_candidate_rows(
            retrieval_query=retrieval_query,
            candidate_limit=broad_candidate_limit,
            faq_only=True,
            enrichment=None,
            use_query_filter=False,
            query_vector=db_side_query_vec,
        )
        rows_by_id = {row["chunk_id"]: row for row in rows}
        for row in broad_rows:
            rows_by_id.setdefault(row["chunk_id"], row)
        rows = list(rows_by_id.values())
        candidate_scope = "faq_broad"

    if not rows and prefer_faq:
        rows = _fetch_candidate_rows(
            retrieval_query=retrieval_query,
            candidate_limit=candidate_limit,
            faq_only=False,
            enrichment=enrichment,
            use_query_filter=True,
            query_vector=db_side_query_vec,
        )
        candidate_scope = "all"

    results = hybrid_rank_documents(
        query_vector=query_vec,
        query_text=retrieval_query,
        rows=rows,
        top_k=k,
    )
    for result in results:
        result["candidate_scope"] = candidate_scope
    return results


@tool(parse_docstring=True)
def refine_retrieval_query(text: str) -> str:
    """Compatibility wrapper around refine_query_text for tool traces.

    Args:
        text: Raw customer question or enriched query.
    """
    refined = refine_query_text(text)
    log_event(
        EVENT_TOOL_COMPLETED,
        tool_name="refine_retrieval_query",
        metadata={"input_length": len(text), "output_length": len(refined)},
    )
    return refined


@tool(parse_docstring=True)
def embed_query(text: str) -> str:
    """Generate an embedding vector for the query text.

    Args:
        text: Query text to embed.
    """
    log_event(
        EVENT_TOOL_STARTED,
        tool_name="embed_query",
        metadata={"text_length": len(text)},
    )
    client = OpenAIEmbeddings(
        model=_embedding_model_name(),
        api_key=os.environ.get("LLM_API_KEY"),
    )
    vector = client.embed_query(text)
    log_event(
        EVENT_TOOL_COMPLETED,
        tool_name="embed_query",
        metadata={"vector_size": len(vector)},
    )
    return json.dumps(vector)


@tool(parse_docstring=True)
def search_documents(embedding_json: str, query_text: str = "", top_k: int | None = None) -> str:
    """Compatibility wrapper around search_document_chunks.

    Args:
        embedding_json: JSON-encoded float list produced by embed_query.
        query_text: Original query text for BM25 keyword search.
        top_k: Number of top results to return. Defaults to RETRIEVAL_TOP_K.
    """
    retrieval_query = refine_query_text(query_text)
    k = top_k or int(os.environ.get("RETRIEVAL_TOP_K", "3"))
    log_event(
        EVENT_TOOL_STARTED,
        tool_name="search_documents",
        metadata={"query_text": query_text, "retrieval_query": retrieval_query, "top_k": k},
    )

    results = search_document_chunks(
        embedding_json=embedding_json,
        query_text=retrieval_query,
        top_k=k,
        prefer_faq=True,
    )
    log_event(
        EVENT_TOOL_COMPLETED,
        tool_name="search_documents",
        metadata={
            "candidate_scope": results[0].get("candidate_scope") if results else "none",
            "result_count": len(results),
        },
    )
    return json.dumps(results, ensure_ascii=False, indent=2)


@tool(parse_docstring=True)
def rerank_documents(docs_json: str, query: str) -> str:
    """Rerank retrieved documents, with a fallback to the original order.

    Args:
        docs_json: JSON-encoded list of document chunks from search_documents.
        query: Original user query for relevance comparison.
    """
    input_documents = json.loads(docs_json)
    enabled = _env_flag("RERANKER_ENABLED", True)
    if enabled and input_documents:
        try:
            output_documents = _llm_rerank_documents(input_documents, query)
        except Exception:
            output_documents = _fallback_rerank(input_documents)
    else:
        output_documents = _fallback_rerank(input_documents)

    log_event(
        EVENT_TOOL_COMPLETED,
        tool_name="rerank_documents",
        metadata={
            "query_length": len(query),
            "input_count": len(input_documents),
            "output_count": len(output_documents),
            "reranker_enabled": enabled,
            "reranker_model": os.environ.get("RERANKER_MODEL") or os.environ.get("LLM_MODEL"),
        },
    )
    return json.dumps(output_documents, ensure_ascii=False)
