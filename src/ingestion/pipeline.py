import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from dotenv import load_dotenv

from core.logging import configure_logging
from core.resiliency import embedding_request
from ingestion.schemas import Document, EmbeddedChunk, TextChunk
from ingestion.stages import Chunker, DocumentLoader, Embedder, VectorStore

# Load the project-root .env (OpenRouter API key) at import time.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)


class RAGIndexingPipeline:
    """Thin orchestrator that wires the ingestion stages together and
    exposes a single entry point: run(file_path) -> List[EmbeddedChunk]."""

    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    OPENROUTER_EMBEDDING_MODEL = "openai/text-embedding-3-small"
    CHROMA_PERSIST_DIR = "data/processed/chroma"
    CHROMA_COLLECTION_NAME = "aether_wireless_docs"

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        api_key: Optional[str] = None,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        # Resolve API key from argument or environment
        resolved_api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable or api_key parameter is required."
            )

        # Initialize OpenAI SDK pointed directly to OpenRouter
        self.client = OpenAI(
            base_url=self.OPENROUTER_BASE_URL,
            api_key=resolved_api_key,
        )

        # Compose the pipeline stages
        self.stages: Dict[str, Any] = {
            "loader": DocumentLoader(),
            "chunker": Chunker(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
            "embedder": Embedder(
                client=self.client,
                model=self.OPENROUTER_EMBEDDING_MODEL,
            ),
            "store": VectorStore(
                persist_dir=persist_dir or self.CHROMA_PERSIST_DIR,
                collection_name=collection_name or self.CHROMA_COLLECTION_NAME,
            ),
        }

        # Convenience aliases (backward compatibility)
        self.collection = self.stages["store"].collection
        self.vector_store = self.collection

    def load_file(self, file_path: Path) -> Document:
        return self.stages["loader"].run(file_path)

    def chunk_document(self, doc: Document) -> List[TextChunk]:
        return self.stages["chunker"].run(doc)

    def generate_embeddings(
        self, chunks: List[TextChunk], batch_size: int = 32
    ) -> List[EmbeddedChunk]:
        return self.stages["embedder"].run(chunks, batch_size=batch_size)

    def upsert_to_vector_store(self, embedded_chunks: List[EmbeddedChunk]) -> int:
        return self.stages["store"].upsert(embedded_chunks)

    def search(
        self,
        query_text: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Embeds a natural-language query and returns top-K context blocks
        from the persistent ChromaDB store."""
        query_embedding = embedding_request(
            self.client,
            self.OPENROUTER_EMBEDDING_MODEL,
            [query_text],
        ).data[0].embedding

        return self.stages["store"].query(query_embedding, top_k=top_k)

    def run(self, file_path: Path) -> List[EmbeddedChunk]:
        """Executes full ingestion flow for a single target file.

        Idempotent: if the document content hash already exists in the
        vector store, the document is skipped (no re-chunking or API
        costs). If the hash differs, stale chunks are purged first.
        """
        doc = self.stages["loader"].run(file_path)
        content_hash = doc.metadata.get("content_hash")

        existing_hashes = self.stages["store"].get_document_hashes(doc.doc_id)

        if content_hash in existing_hashes:
            logger.info(
                "[Skipped] %s unchanged (hash %s...) — already indexed.",
                doc.doc_id,
                content_hash[:8],
            )
            return []

        if existing_hashes:
            removed = self.stages["store"].delete_document(doc.doc_id)
            logger.info(
                "[Purge] Removed %d stale chunks for '%s' (content changed).",
                removed,
                doc.doc_id,
            )

        chunks = self.stages["chunker"].run(doc)
        embedded_chunks = self.stages["embedder"].run(chunks)
        count = self.stages["store"].upsert(embedded_chunks)
        total = self.stages["store"].count
        logger.info(
            "[Pipeline Success] Indexed %d chunks from: %s",
            count,
            file_path.name,
        )
        logger.info(
            "[Persist] ChromaDB collection '%s' now holds %d chunks",
            self.collection.name,
            total,
        )
        return embedded_chunks

    def run_batch(
        self,
        file_paths: List[Path],
    ) -> Tuple[List[EmbeddedChunk], List[str]]:
        """Ingests many documents with per-file error isolation.

        A failure on one file is logged with its traceback and skipped so
        the remaining documents still get processed. Returns (indexed
        chunks, list of failed file paths).
        """
        all_results: List[EmbeddedChunk] = []
        failed: List[str] = []

        for file_path in file_paths:
            try:
                all_results.extend(self.run(Path(file_path)))
            except Exception:
                logger.exception(
                    "[Skipped] %s failed and was isolated from the batch.",
                    file_path,
                )
                failed.append(str(file_path))

        logger.info(
            "[Batch Complete] %d files ok, %d failed, %d chunks indexed.",
            len(file_paths) - len(failed),
            len(failed),
            len(all_results),
        )
        return all_results, failed

    def run_directory(
        self,
        directory: Path,
        patterns: Tuple[str, ...] = ("*.pdf", "*.txt", "*.md"),
    ) -> Tuple[List[EmbeddedChunk], List[str]]:
        """Convenience wrapper: collects matching files under ``directory``
        (recursive) and ingests them via :meth:`run_batch`."""
        files = sorted(
            fp
            for pattern in patterns
            for fp in Path(directory).rglob(pattern)
        )
        if not files:
            logger.warning(
                "[Batch] No files matched %s under %s",
                patterns,
                directory,
            )
            return [], []
        return self.run_batch(files)


# =====================================================================
# PIPELINE EXECUTION FOR AETHER WIRELESS
# =====================================================================

def main() -> None:
    """CLI entry point: ingests a target document and runs a sanity search."""
    # Define relative path to the requested PDF document
    target_pdf = Path("data/raw/billing/AW-BIL-001_billing_dispute_policy.pdf")

    configure_logging()

    # Initialize and execute pipeline
    pipeline = RAGIndexingPipeline(chunk_size=500, chunk_overlap=50)

    try:
        results = pipeline.run(target_pdf)

        if results:
            # Inspect the first chunk extracted from the PDF
            logger.info("--- First Chunk Extracted from PDF ---")
            logger.info("Chunk ID: %s", results[0].chunk_id)
            logger.info("Category: %s", results[0].metadata.get("category"))
            logger.info("Text snippet: %r...", results[0].text[:200])

        # Sanity check: query the persistent store it was just written to
        logger.info("--- Sanity Search ---")
        hits = pipeline.search("how long does a billing dispute investigation take?")
        ids = hits.get("ids", [[]])[0]
        logger.info("Top-K hit ids: %s", ids[:3])
    except FileNotFoundError:
        logger.error(
            "[Error] File not found at %s. Please ensure the PDF is placed in the sub-folder.",
            target_pdf,
        )


if __name__ == "__main__":
    main()