"""
main.py
CLI entrypoint for triggering the RAG indexing pipeline and related operations.
"""
import argparse
import sys

from core.config import settings
from core.database import DatabaseManager
from core.logging import get_logger, setup_logging
from indexing.builder import run_indexing_pipeline
from loaders.filesystem import FilesystemLoader

logger = get_logger(__name__)


def cmd_index(args: argparse.Namespace) -> None:
    """Run source ingestion, vector index synchronization, and soft-deletion cleanup."""
    setup_logging()
    logger.info(
        "Starting indexing command",
        source_dir=args.source_dir,
        recursive=args.recursive,
    )

    db_manager = DatabaseManager()
    loader = FilesystemLoader(directory_path=args.source_dir, recursive=args.recursive)

    embedded_chunks = run_indexing_pipeline(loader=loader, db_manager=db_manager)

    logger.info(
        "Indexing command completed",
        embedded_chunks=len(embedded_chunks),
        vector_store_provider=settings.VECTOR_STORE_PROVIDER,
    )
    print(f"Indexed {len(embedded_chunks)} chunks.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="RAGOps indexing pipeline CLI.")
    subparsers = parser.add_subparsers(dest="command")

    index_parser = subparsers.add_parser(
        "index",
        help="Run source ingestion, vector index synchronization, and soft-deletion cleanup.",
    )
    index_parser.add_argument(
        "--source-dir", "-s",
        required=True,
        help="Directory containing source files to ingest.",
    )
    index_parser.add_argument(
        "--recursive/--no-recursive",
        dest="recursive",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Scan subdirectories recursively. (default: recursive)",
    )
    index_parser.set_defaults(func=cmd_index)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()