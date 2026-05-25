"""CLI entrypoint for rebuilding document chunks and embeddings."""

from __future__ import annotations

import argparse
import logging

from .pipeline import run_documents_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build documents_chunks and documents_embeddings from documents.")
    parser.add_argument("--document-id", dest="document_id")
    parser.add_argument("--source-type", dest="source_type")
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))

    result = run_documents_pipeline(
        document_id=args.document_id,
        source_type=args.source_type,
        category=args.category,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print(f"documents={result.total_documents}")
    print(f"processed={result.processed_documents}")
    print(f"skipped={result.skipped_documents}")
    print(f"failed={result.failed_documents}")
    print(f"chunks={result.total_chunks}")
    print(f"embeddings={result.total_embeddings}")
    for item in result.results:
        status = "ok"
        detail = ""
        if item.skipped:
            status = "skipped"
            detail = item.skip_reason or ""
        elif not item.success:
            status = "failed"
            detail = item.error or ""
        print(f"{item.document_id}\t{status}\tchunks={item.chunk_count}\tembeddings={item.embedding_count}\t{detail}".rstrip())

    return 1 if result.failed_documents else 0


if __name__ == "__main__":
    raise SystemExit(main())
