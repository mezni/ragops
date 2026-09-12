"""Command-line interface for the Aether Wireless RAG pipeline.

Canonical entry point shared by the ``ragops`` console script, the root
``main.py``, and ``python -m ingestion.pipeline``.
"""

import argparse
import logging
from pathlib import Path
from typing import Optional, Sequence

from ingestion import FileSystemSource, RAGIndexingPipeline, configure_logging

logger = logging.getLogger(__name__)

DEFAULT_QUERY = "how long does a billing dispute investigation take?"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ragops",
        description="Aether Wireless RAG ingestion pipeline.",
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        default="data/raw",
        help="Directory to scan recursively (default: data/raw)",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help=f"Sanity search query (default: {DEFAULT_QUERY!r})",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of search hits to log (default: 3)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Chunk size in characters (default: 500)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Chunk overlap in characters (default: 50)",
    )
    parser.add_argument(
        "--patterns",
        nargs="*",
        default=None,
        help="Glob patterns to match, e.g. '*.pdf *.txt' (default: all supported formats)",
    )
    parser.add_argument(
        "--persist-dir",
        default="data/processed/chroma",
        help="ChromaDB persistence directory (default: data/processed/chroma)",
    )
    parser.add_argument(
        "--no-search",
        action="store_true",
        help="Skip the sanity search after ingestion",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Runs ingestion over an input directory, then a sanity search."""
    args = build_parser().parse_args(argv)
    configure_logging()

    patterns = tuple(args.patterns) if args.patterns else None
    source = FileSystemSource(
        args.input_dir,
        patterns=patterns or FileSystemSource.DEFAULT_PATTERNS,
    )

    try:
        pipeline = RAGIndexingPipeline(
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            persist_dir=args.persist_dir,
        )
    except ValueError as exc:
        logger.error("[Error] %s", exc)
        return 2

    try:
        results, failed = pipeline.ingest_source(source)
    except FileNotFoundError:
        logger.error("[Error] Input directory not found: %s", args.input_dir)
        return 2

    if results:
        first = results[0]
        logger.info("--- First Chunk Extracted ---")
        logger.info("Chunk ID: %s", first.chunk_id)
        logger.info("Category: %s", first.metadata.get("category"))
        logger.info("Source: %s", first.metadata.get("data_source"))
        logger.info("Text snippet: %r...", first.text[:200])
    elif failed:
        logger.error(
            "[Error] No documents indexed; %d file(s) failed.",
            len(failed),
        )

    if not args.no_search:
        if pipeline.collection.count() > 0:
            logger.info("--- Sanity Search ---")
            hits = pipeline.search(args.query, top_k=args.top_k)
            ids = hits.get("ids", [[]])[0]
            documents = hits.get("documents", [[]])[0]
            logger.info("Top-K hit ids: %s", ids[: args.top_k])
            for chunk_id, text in zip(ids[: args.top_k], documents[: args.top_k]):
                logger.info("  - %s: %r...", chunk_id, text[:120])
        else:
            logger.warning("[Search] Skipped — the collection is empty.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())