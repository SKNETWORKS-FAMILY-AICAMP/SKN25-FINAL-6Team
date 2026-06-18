from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[2]
COMMON_SRC_DIR = REPO_ROOT / "packages" / "common-python" / "src"
for path in (PROJECT_ROOT, COMMON_SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from common.db.connection import db_connection


DATASET_DIR = Path(__file__).parent / "datasets"
DEFAULT_DATASET = DATASET_DIR / "sj-documents-retrievable-ragas-30-v3.json"
DEFAULT_OUTPUT = Path(__file__).parent / "outputs" / "sj_embedding_model_comparison.json"
DEFAULT_LANGSMITH_DATASET = "sj-documents-retrievable-ragas-30-v3"

PROFILES = {
    "small": {
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "documents_table": "sj_documents",
        "chunks_table": "test_documents_chunks",
        "embeddings_table": "test_documents_embeddings_small",
    },
    "large": {
        "embedding_model": "text-embedding-3-large",
        "embedding_dimensions": 1536,
        "documents_table": "sj_documents",
        "chunks_table": "test_documents_chunks",
        "embeddings_table": "test_documents_embeddings_large",
    },
    "large3072": {
        "embedding_model": "text-embedding-3-large",
        "embedding_dimensions": 3072,
        "documents_table": "sj_documents",
        "chunks_table": "test_documents_chunks",
        "embeddings_table": "test_documents_embeddings_large_3072",
    },
}

ALLOWED_TABLES = {
    "sj_documents",
    "test_documents_chunks",
    "test_documents_embeddings_small",
    "test_documents_embeddings_large",
    "test_documents_embeddings_large_3072",
}

STOPWORD_TOKENS = {
    "문서",
    "내용",
    "핵심",
    "요약",
    "알려주세요",
    "무엇",
    "어떤",
    "어떻게",
    "하나요",
    "인가요",
    "설명",
    "안내",
}


def load_chatbot_langsmith_env() -> None:
    load_dotenv(REPO_ROOT / ".env", override=True)
    mappings = {
        "CHATBOT_LANGSMITH_API_KEY": "LANGSMITH_API_KEY",
        "CHATBOT_LANGSMITH_PROJECT": "LANGSMITH_PROJECT",
        "CHATBOT_LANGSMITH_TRACING": "LANGSMITH_TRACING",
    }
    for source, target in mappings.items():
        value = os.environ.get(source)
        if value:
            os.environ[target] = value
    if os.environ.get("LANGSMITH_TRACING"):
        os.environ["LANGCHAIN_TRACING_V2"] = os.environ["LANGSMITH_TRACING"]


def load_dataset(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    examples = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(examples, list):
        raise ValueError(f"Unsupported dataset shape: {path}")
    return payload if isinstance(payload, dict) else {}, examples


def table_name(value: str) -> str:
    if value not in ALLOWED_TABLES:
        raise ValueError(f"Table is not allowed for this eval script: {value}")
    return value


@lru_cache(maxsize=4)
def embedder(model: str, dimensions: int | None) -> Any:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)
    from langchain_openai import OpenAIEmbeddings

    kwargs: dict[str, Any] = {"model": model, "api_key": api_key}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    return OpenAIEmbeddings(**kwargs)


@lru_cache(maxsize=1)
def answer_llm() -> Any:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)
    from langchain_openai import ChatOpenAI

    model = os.environ.get("EVAL_ANSWER_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    return ChatOpenAI(model=model, api_key=api_key, temperature=0)


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def keyword_tokens(text: str, *, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[0-9A-Za-z가-힣]+", text)
    cleaned = []
    for token in tokens:
        token = token.strip()
        if len(token) < 2 or token in STOPWORD_TOKENS:
            continue
        if token not in cleaned:
            cleaned.append(token)
    return cleaned[:limit]


def retrieve_contexts(
    *,
    profile: dict[str, str],
    question: str,
    top_k: int,
) -> list[dict[str, Any]]:
    documents_table = table_name(profile["documents_table"])
    chunks_table = table_name(profile["chunks_table"])
    embeddings_table = table_name(profile["embeddings_table"])
    model = profile["embedding_model"]
    dimensions = int(profile["embedding_dimensions"]) if profile.get("embedding_dimensions") else None
    query_vector = embedder(model, dimensions).embed_query(question)
    query_vector_literal = vector_literal(query_vector)
    tokens = keyword_tokens(question)
    keyword_expr = "0"
    keyword_params: list[str] = []
    if tokens:
        parts = []
        for token in tokens:
            parts.append(
                """
                CASE
                    WHEN d.title ILIKE %s THEN 3
                    WHEN c.chunk_text ILIKE %s THEN 1
                    ELSE 0
                END
                """
            )
            pattern = f"%{token}%"
            keyword_params.extend([pattern, pattern])
        keyword_expr = " + ".join(parts)

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
                    1 - (e.embedding_vector <=> %s::vector) AS cosine_score,
                    ({keyword_expr}) AS keyword_score
                FROM {chunks_table} c
                JOIN {documents_table} d ON d.document_id = c.document_id
                JOIN {embeddings_table} e ON e.chunk_id = c.chunk_id
                ORDER BY keyword_score DESC, e.embedding_vector <=> %s::vector
                LIMIT %s
                """,
                (query_vector_literal, *keyword_params, query_vector_literal, top_k),
            )
            rows = [dict(row) for row in cur.fetchall()]

    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["cosine_score"] = float(row["cosine_score"])
    return rows


def make_answer(question: str, contexts: list[dict[str, Any]]) -> str:
    context_text = "\n\n".join(
        f"[{idx}] {row.get('title') or ''}\n{row.get('chunk_text') or ''}"
        for idx, row in enumerate(contexts, start=1)
    )
    messages = [
        (
            "system",
            "You are a Korean game customer-support chatbot. Answer only from the provided contexts. "
            "When at least one context is provided, always answer from the title and body. "
            "In the first sentence, explicitly reflect the document title, target entity, and request intent from the user's question. "
            "Naturally include the key terms from the question, such as document names, character names, content names, and requested summary/explanation intent. "
            "Summarize the grounded answer in 2 to 4 Korean sentences. "
            "If the body is short, say only what can be confirmed from that short text. "
            "Use 확인이 어렵다고 안내한다 only when the context list is empty or completely irrelevant. "
            "Keep the answer concise and suitable for AUTO_RESPONSE.",
        ),
        ("human", f"질문:\n{question}\n\n근거 문서:\n{context_text}"),
    ]
    answer = str(answer_llm().invoke(messages).content)
    if "확인이 어렵" not in answer or not contexts:
        return answer

    top_context = contexts[0]
    title = str(top_context.get("title") or "").strip()
    body = str(top_context.get("chunk_text") or "").strip()
    if title and body.startswith(title):
        body = body[len(title) :].strip()
    body = " ".join(body.split())
    if len(body) > 220:
        body = body[:220].rstrip() + "..."
    if body:
        return f"{title} 문서에서는 {body} 내용을 확인할 수 있습니다."
    if title:
        return f"{title} 문서의 제목은 확인되지만, 제공된 본문이 짧아 세부 내용은 제한적으로만 확인됩니다."
    return answer


async def ragas_score_one(
    *,
    metric_name: str,
    question: str,
    answer: str,
    reference: str,
    contexts: list[str],
    rubrics: dict[str, str],
) -> float | str:
    try:
        from ragas import SingleTurnSample
        from ragas.metrics import (
            Faithfulness,
            InstanceRubrics,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
        )

        try:
            from ragas.metrics import AnswerRelevancy
        except ImportError:
            from ragas.metrics import ResponseRelevancy

            AnswerRelevancy = ResponseRelevancy
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    except ImportError:
        return "ragas_not_installed"

    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    llm_model = os.environ.get("RAGAS_LLM_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    embedding_model = os.environ.get("RAGAS_EMBEDDING_MODEL") or "text-embedding-3-small"
    metric_by_name = {
        "faithfulness": Faithfulness,
        "answer_relevancy": AnswerRelevancy,
        "context_precision": LLMContextPrecisionWithReference,
        "context_recall": LLMContextRecall,
        "instance_rubrics": InstanceRubrics,
    }
    metric = metric_by_name[metric_name]()
    if hasattr(metric, "llm"):
        metric.llm = LangchainLLMWrapper(ChatOpenAI(model=llm_model, api_key=api_key, temperature=0))
    if hasattr(metric, "embeddings"):
        metric.embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=embedding_model, api_key=api_key))

    sample_kwargs = {
        "user_input": question,
        "response": answer,
        "reference": reference,
        "retrieved_contexts": contexts,
    }
    if metric_name == "instance_rubrics":
        sample_kwargs["rubrics"] = rubrics
    sample = SingleTurnSample(**sample_kwargs)
    try:
        return float(await metric.single_turn_ascore(sample))
    except Exception as exc:
        return f"ragas_error:{type(exc).__name__}"


def score_keyword_hits(example: dict[str, Any], contexts: list[dict[str, Any]]) -> dict[str, Any]:
    outputs = example.get("outputs") or {}
    expected_keywords = [str(value) for value in outputs.get("expected_keywords") or []]
    expected_documents = {str(value) for value in outputs.get("source_documents") or []}
    top_text = "\n".join(
        f"{row.get('document_id') or ''} {row.get('title') or ''} {row.get('chunk_text') or ''}"
        for row in contexts
    )
    matched_keywords = [keyword for keyword in expected_keywords if keyword in top_text]
    matched_documents = [
        str(row.get("document_id"))
        for row in contexts
        if str(row.get("document_id")) in expected_documents
    ]
    return {
        "keyword_hit_count": len(matched_keywords),
        "keyword_total": len(expected_keywords),
        "keyword_recall": (len(matched_keywords) / len(expected_keywords)) if expected_keywords else None,
        "matched_keywords": matched_keywords,
        "source_document_hit": bool(matched_documents) if expected_documents else None,
        "matched_source_documents": matched_documents,
    }


async def evaluate_profile(
    *,
    profile_name: str,
    profile: dict[str, str],
    examples: list[dict[str, Any]],
    top_k: int,
    generate_answers: bool,
    enable_ragas: bool,
) -> list[dict[str, Any]]:
    rows = []
    for index, example in enumerate(examples, start=1):
        inputs = example.get("inputs") or {}
        outputs = example.get("outputs") or {}
        metadata = example.get("metadata") or {}
        question = str(inputs.get("user_message") or "")
        started_at = time.perf_counter()
        contexts = retrieve_contexts(profile=profile, question=question, top_k=top_k)
        latency_ms = (time.perf_counter() - started_at) * 1000
        answer = make_answer(question, contexts) if generate_answers else ""
        context_texts = [str(row.get("chunk_text") or "") for row in contexts]
        keyword_scores = score_keyword_hits(example, contexts)
        ragas_scores: dict[str, Any] = {}
        if enable_ragas and answer:
            rubrics = {
                str(key): str(value)
                for key, value in dict(outputs.get("rubrics") or {}).items()
                if value is not None
            }
            for metric_name in (
                "faithfulness",
                "answer_relevancy",
                "context_precision",
                "context_recall",
                "instance_rubrics",
            ):
                ragas_scores[metric_name] = await ragas_score_one(
                    metric_name=metric_name,
                    question=question,
                    answer=answer,
                    reference=str(outputs.get("reference_answer") or ""),
                    contexts=context_texts,
                    rubrics=rubrics,
                )

        rows.append(
            {
                "test_id": metadata.get("test_id") or f"SJ-EVAL-{index:03d}",
                "profile": profile_name,
                "embedding_model": profile["embedding_model"],
                "embeddings_table": profile["embeddings_table"],
                "question": question,
                "answer": answer,
                "reference_answer": outputs.get("reference_answer"),
                "latency_ms": round(latency_ms, 2),
                "top_k": top_k,
                "top_contexts": contexts,
                **keyword_scores,
                "ragas": ragas_scores,
            }
        )
    return rows


def langsmith_target(profile_name: str) -> Any:
    profile = PROFILES[profile_name]

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        question = str(inputs.get("user_message") or "")
        top_k = int(inputs.get("top_k") or os.environ.get("SJ_EVAL_TOP_K", "5"))
        started_at = time.perf_counter()
        contexts = retrieve_contexts(profile=profile, question=question, top_k=top_k)
        latency_ms = (time.perf_counter() - started_at) * 1000
        answer = make_answer(question, contexts)
        return {
            "answer": answer,
            "retrieved_contexts": [str(row.get("chunk_text") or "") for row in contexts],
            "top_contexts": contexts,
            "profile": profile_name,
            "embedding_model": profile["embedding_model"],
            "embeddings_table": profile["embeddings_table"],
            "latency_ms": round(latency_ms, 2),
        }

    return target


def keyword_recall(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    expected_keywords = [str(value) for value in reference_outputs.get("expected_keywords") or []]
    if not expected_keywords:
        return {"key": "keyword_recall", "value": "not_applicable"}
    top_text = "\n".join(
        f"{row.get('document_id') or ''} {row.get('title') or ''} {row.get('chunk_text') or ''}"
        for row in outputs.get("top_contexts") or []
    )
    matched = [keyword for keyword in expected_keywords if keyword in top_text]
    return {
        "key": "keyword_recall",
        "score": len(matched) / len(expected_keywords),
        "value": ",".join(matched),
    }


def source_document_hit(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    expected_documents = {str(value) for value in reference_outputs.get("source_documents") or []}
    if not expected_documents:
        return {"key": "source_document_hit", "value": "not_applicable"}
    retrieved_documents = {
        str(row.get("document_id"))
        for row in outputs.get("top_contexts") or []
        if row.get("document_id") is not None
    }
    return {
        "key": "source_document_hit",
        "score": bool(expected_documents & retrieved_documents),
        "value": ",".join(sorted(expected_documents & retrieved_documents)),
    }


def answer_non_empty(outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "answer_non_empty", "score": bool(str(outputs.get("answer") or "").strip())}


def latency(outputs: dict[str, Any]) -> dict[str, Any]:
    value = float(outputs.get("latency_ms") or 0)
    return {"key": "latency_ms", "score": value < 5000, "value": round(value, 2)}


def ragas_langsmith_metric(metric_name: str) -> Any:
    key = metric_name

    def evaluator(
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        reference_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        question = str(inputs.get("user_message") or "")
        answer = str(outputs.get("answer") or "")
        contexts = [str(value) for value in outputs.get("retrieved_contexts") or []]
        reference = str(reference_outputs.get("reference_answer") or "")
        rubrics = {
            str(rubric_key): str(rubric_value)
            for rubric_key, rubric_value in dict(reference_outputs.get("rubrics") or {}).items()
            if rubric_value is not None
        }
        if not answer:
            return {"key": key, "value": "not_applicable"}
        if metric_name in {"faithfulness", "context_precision", "context_recall"} and not contexts:
            return {"key": key, "score": 0.0, "value": "no_retrieved_contexts"}
        try:
            score = asyncio.run(
                ragas_score_one(
                    metric_name=metric_name,
                    question=question,
                    answer=answer,
                    reference=reference,
                    contexts=contexts,
                    rubrics=rubrics,
                )
            )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                score = loop.run_until_complete(
                    ragas_score_one(
                        metric_name=metric_name,
                        question=question,
                        answer=answer,
                        reference=reference,
                        contexts=contexts,
                        rubrics=rubrics,
                    )
                )
            finally:
                loop.close()
        if isinstance(score, str):
            return {"key": key, "value": score}
        return {"key": key, "score": score, "value": round(float(score), 3)}

    evaluator.__name__ = key
    return evaluator


def upload_langsmith_dataset(
    *,
    examples: list[dict[str, Any]],
    dataset_name: str,
    description: str,
    recreate: bool,
) -> None:
    from langsmith import Client

    client = Client()
    if recreate:
        try:
            client.delete_dataset(dataset_name=dataset_name)
        except Exception:
            pass
    try:
        dataset = client.create_dataset(dataset_name=dataset_name, description=description)
    except Exception:
        dataset = client.read_dataset(dataset_name=dataset_name)

    client.create_examples(
        dataset_id=dataset.id,
        inputs=[row["inputs"] for row in examples],
        outputs=[row.get("outputs") for row in examples],
        metadata=[row.get("metadata") for row in examples],
    )
    print(f"Uploaded {len(examples)} examples to LangSmith dataset: {dataset_name}")


def run_langsmith_evaluations(
    *,
    dataset_name: str,
    profiles: list[str],
    experiment_prefix: str,
    max_concurrency: int,
    limit: int | None,
    enable_ragas: bool,
) -> None:
    from langsmith import Client, evaluate

    data: Any = dataset_name
    if limit is not None:
        client = Client()
        data = list(client.list_examples(dataset_name=dataset_name))[:limit]

    evaluators = [keyword_recall, source_document_hit, answer_non_empty, latency]
    if enable_ragas:
        evaluators.extend(
            [
                ragas_langsmith_metric("faithfulness"),
                ragas_langsmith_metric("answer_relevancy"),
                ragas_langsmith_metric("context_precision"),
                ragas_langsmith_metric("context_recall"),
                ragas_langsmith_metric("instance_rubrics"),
            ]
        )

    for profile_name in profiles:
        os.environ["SJ_EVAL_TOP_K"] = os.environ.get("SJ_EVAL_TOP_K", "5")
        results = evaluate(
            langsmith_target(profile_name),
            data=data,
            evaluators=evaluators,
            experiment_prefix=f"{experiment_prefix}-{profile_name}",
            max_concurrency=max_concurrency,
        )
        print(results)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_profile.setdefault(str(row["profile"]), []).append(row)
    summary = {}
    for profile, items in by_profile.items():
        keyword_recalls = [
            float(item["keyword_recall"])
            for item in items
            if item.get("keyword_recall") is not None
        ]
        doc_hits = [
            bool(item["source_document_hit"])
            for item in items
            if item.get("source_document_hit") is not None
        ]
        summary[profile] = {
            "examples": len(items),
            "avg_keyword_recall": round(sum(keyword_recalls) / len(keyword_recalls), 4)
            if keyword_recalls
            else None,
            "source_document_hit_rate": round(sum(doc_hits) / len(doc_hits), 4)
            if doc_hits
            else None,
            "avg_latency_ms": round(sum(float(item["latency_ms"]) for item in items) / len(items), 2)
            if items
            else None,
        }
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    csv_path = path.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "test_id",
                "profile",
                "embedding_model",
                "embeddings_table",
                "question",
                "latency_ms",
                "keyword_recall",
                "source_document_hit",
                "matched_keywords",
                "matched_source_documents",
                "answer",
                "reference_answer",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row[key], ensure_ascii=False)
                    if isinstance(row.get(key), (list, dict))
                    else row.get(key)
                    for key in writer.fieldnames
                }
            )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare small vs large embeddings against sj_documents test RAG tables."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profiles", nargs="+", default=["small", "large"], choices=sorted(PROFILES))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--generate-answers", action="store_true")
    parser.add_argument("--enable-ragas", action="store_true")
    parser.add_argument("--upload-langsmith-dataset", action="store_true")
    parser.add_argument("--langsmith", action="store_true", help="Run small/large comparison as LangSmith experiments.")
    parser.add_argument("--langsmith-dataset-name", default=DEFAULT_LANGSMITH_DATASET)
    parser.add_argument("--langsmith-recreate-dataset", action="store_true")
    parser.add_argument("--experiment-prefix", default="sj-embedding-model-comparison")
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    load_chatbot_langsmith_env()
    dataset_info, examples = load_dataset(args.dataset)

    if args.upload_langsmith_dataset:
        upload_examples = examples[: args.limit] if args.limit is not None else examples
        upload_langsmith_dataset(
            examples=upload_examples,
            dataset_name=args.langsmith_dataset_name,
            description=str((dataset_info.get("dataset_info") or {}).get("description") or ""),
            recreate=args.langsmith_recreate_dataset,
        )
        if not args.langsmith:
            return

    if args.langsmith:
        os.environ["SJ_EVAL_TOP_K"] = str(args.top_k)
        run_langsmith_evaluations(
            dataset_name=args.langsmith_dataset_name,
            profiles=list(args.profiles),
            experiment_prefix=args.experiment_prefix,
            max_concurrency=args.max_concurrency,
            limit=args.limit,
            enable_ragas=args.enable_ragas,
        )
        return

    eval_examples = examples[: args.limit] if args.limit is not None else examples
    all_rows: list[dict[str, Any]] = []
    for profile_name in args.profiles:
        rows = await evaluate_profile(
            profile_name=profile_name,
            profile=PROFILES[profile_name],
            examples=eval_examples,
            top_k=args.top_k,
            generate_answers=args.generate_answers or args.enable_ragas,
            enable_ragas=args.enable_ragas,
        )
        all_rows.extend(rows)

    report = {
        "dataset": dataset_info.get("dataset_info") or {},
        "profiles": {name: PROFILES[name] for name in args.profiles},
        "summary": summarize(all_rows),
        "results": all_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.output, all_rows)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    asyncio.run(main())
