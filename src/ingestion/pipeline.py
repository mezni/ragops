import logging
import os
import uuid
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from dotenv import load_dotenv

from core.config import get_settings
from core.resiliency import embedding_request
from ingestion.schemas import Document, EmbeddedChunk, TextChunk
from ingestion.sources import DocumentSource, FileSystemSource
from ingestion.stages import (
    Chunker,
    DocumentLoader,
    DocumentRegistry,
    Embedder,
    VectorStore,
)

# Load the project-root .env (OpenRouter API key) at import time.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

_settings = get_settings()


def pipeline_version() -> str:
    """Semantic version of the ingestion codebase, for audit lineage.

    Falls back to ``"dev"`` when the package hasn't been installed.
    """
    try:
        return f"v{_pkg_version('ragops')}"
    except PackageNotFoundError:
        return "dev"


class RAGIndexingPipeline:
    """Thin orchestrator that wires the ingestion stages together and
    exposes a single entry point: run(file_path) -> List[EmbeddedChunk]."""

    # Centralized defaults (see ragops.toml / src/core/config.py).
    OPENROUTER_BASE_URL = _settings.embedding.openrouter_base_url
    OPENROUTER_EMBEDDING_MODEL = _settings.embedding.model
    CHROMA_PERSIST_DIR = _settings.chroma.persist_dir
    CHROMA_COLLECTION_NAME = _settings.chroma.collection_name

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
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

        cfg = get_settings()

        # Initialize OpenAI SDK pointed directly to OpenRouter
        self.client = OpenAI(
            base_url=self.OPENROUTER_BASE_URL,
            api_key=resolved_api_key,
        )

        # Compose the pipeline stages
        resolved_persist_dir = persist_dir or self.CHROMA_PERSIST_DIR
        resolved_collection_name = collection_name or self.CHROMA_COLLECTION_NAME
        self.stages: Dict[str, Any] = {
            "loader": DocumentLoader(),
            "chunker": Chunker(
                chunk_size=(
                    chunk_size if chunk_size is not None else cfg.chunking.chunk_size
                ),
                chunk_overlap=(
                    chunk_overlap
                    if chunk_overlap is not None
                    else cfg.chunking.chunk_overlap
                ),
            ),
            "embedder": Embedder(
                client=self.client,
                model=self.OPENROUTER_EMBEDDING_MODEL,
            ),
            "store": VectorStore(
                persist_dir=resolved_persist_dir,
                collection_name=resolved_collection_name,
            ),
            "registry": DocumentRegistry(
                persist_dir=resolved_persist_dir,
                collection_name=resolved_collection_name,
            ),
        }

        # Convenience aliases (backward compatibility)
        self.collection = self.stages["store"].collection
        self.vector_store = self.collection
        self.registry = self.stages["registry"]

    def load_file(self, file_path: Path) -> Document:
        return self.stages["loader"].run(file_path)

    def chunk_document(self, doc: Document) -> List[TextChunk]:
        return self.stages["chunker"].run(doc)

    def generate_embeddings(
        self, chunks: List[TextChunk], batch_size: Optional[int] = None
    ) -> List[EmbeddedChunk]:
        return self.stages["embedder"].run(
            chunks,
            batch_size=batch_size or get_settings().embedding.batch_size,
        )

    def upsert_to_vector_store(self, embedded_chunks: List[EmbeddedChunk]) -> int:
        return self.stages["store"].upsert(embedded_chunks)

    def search(
        self,
        query_text: str,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Embeds a natural-language query and returns top-K context blocks
        from the persistent ChromaDB store."""
        query_embedding = embedding_request(
            self.client,
            self.OPENROUTER_EMBEDDING_MODEL,
            [query_text],
        ).data[0].embedding

        return self.stages["store"].query(
            query_embedding,
            top_k=top_k or get_settings().search.top_k,
        )

    def run(self, file_path: Path, job_id: Optional[str] = None) -> List[EmbeddedChunk]:
        """Executes full ingestion flow for a single target file.

        Versioned and idempotent: a brand-new document is indexed as
        version 0 with ``is_active=True``; an unchanged document is
        skipped; a modified document is indexed as the next version
        (old chunks stay in the store but are deactivated, so they can
        be rolled back later). Every indexed chunk is stamped with the
        ``job_id`` (generated if absent) and the pipeline version.
        """
        if job_id is None:
            job_id = str(uuid.uuid4())
        doc = self.stages["loader"].run(file_path)
        return self._index_document(doc, job_id)

    def _index_document(self, doc: Document, job_id: str) -> List[EmbeddedChunk]:
        """Shared indexing core: version decision, chunk, embed, persist."""
        store = self.stages["store"]
        registry = self.stages["registry"]
        content_hash = doc.metadata.content_hash
        data_source = doc.metadata.data_source

        record = registry.get(doc.doc_id)

        # Brand-new document -> version 0.
        if record is None:
            version = 0
        else:
            active_version = record.get("active_version")
            unchanged = any(
                v.get("version") == active_version
                and v.get("content_hash") == content_hash
                for v in record.get("versions", [])
            )
            if unchanged:
                if record.get("is_active"):
                    logger.info(
                        "[Skipped] %s unchanged (hash %s...) — already indexed as v%d.",
                        doc.doc_id,
                        content_hash[:get_settings().logging.hash_preview_len],
                        active_version,
                    )
                    return []
                # File reappeared with identical content -> reactivate same version.
                store.activate_version(doc.doc_id, active_version)
                registry.set_active(doc.doc_id, True)
                logger.info(
                    "[Reactivated] %s restored to active version %d.",
                    doc.doc_id,
                    active_version,
                )
                return []

            # Content changed -> increment version, retire the old chunks.
            store.deactivate_document(doc.doc_id)
            version = max(
                (v.get("version", -1) for v in record.get("versions", [])),
                default=-1,
            ) + 1
            logger.info(
                "[Version] %s changed — indexing as version %d (old chunks retired, not deleted).",
                doc.doc_id,
                version,
            )

        chunks = self.stages["chunker"].run(doc)
        # Version-scope chunk IDs so a later version never overwrites this
        # one: rollback needs every version's content preserved in the store.
        for idx, chunk in enumerate(chunks):
            chunk.chunk_id = f"{doc.doc_id}_v{version}_chunk_{idx}"
            chunk.metadata.version = version
            chunk.metadata.is_active = True
        embedded_chunks = self.stages["embedder"].run(chunks)
        count = store.upsert(embedded_chunks, version=version, is_active=True)
        registry.register_version(
            doc_id=doc.doc_id,
            content_hash=content_hash,
            locator=doc.source,
            data_source=data_source,
        )
        total = store.count
        logger.info(
            "[Pipeline Success] Indexed %d chunks from: %s (source=%s, version=%d)",
            count,
            doc.source,
            data_source,
            version,
        )
        logger.info(
            "[Persist] ChromaDB collection '%s' now holds %d chunks",
            self.collection.name,
            total,
        )
        return embedded_chunks

    def rollback(self, doc_id: str, version: int) -> int:
        """Rolls a document back to an earlier version.

        The target version's chunks are re-activated; every other version
        is deactivated. Versioned content is kept in the store, so this is
        an instant metadata flip — no re-embedding, no file required.
        Returns the number of chunks now active for ``doc_id``.
        """
        record = self.registry.get(doc_id)
        if record is None:
            raise KeyError(f"No registry entry for doc '{doc_id}'.")
        known = {v.get("version") for v in record.get("versions", [])}
        if version not in known:
            raise ValueError(
                f"'{doc_id}' has versions {sorted(known)}; cannot roll back to {version}."
            )

        active = self.stages["store"].activate_version(doc_id, version)
        self.registry.set_active_version(doc_id, version)
        logger.info(
            "[Rollback] %s -> version %d (%d chunks re-activated).",
            doc_id,
            version,
            active,
        )
        return active

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

    def ingest_source(
        self,
        source: DocumentSource,
    ) -> Tuple[List[EmbeddedChunk], List[str]]:
        """Ingests every document discovered by ``source``.

        Documents are discovered (e.g. ``FileSystemSource`` scans the
        directory tree recursively); each reference is loaded, stamped
        with its ``data_source``, and indexed individually so a single
        broken document never aborts the source. After ingestion, any
        previously-active document this source no longer provides is
        marked inactive (``is_active=False``), so deleted files stop
        surfacing in answers but stay retrievable for rollback. Returns
        (indexed chunks, list of failed locators).
        """
        references = source.discover()
        all_results: List[EmbeddedChunk] = []
        failed: List[str] = []
        discovered = {ref.locator for ref in references}

        for ref in references:
            try:
                doc = self.stages["loader"].from_reference(ref)
                all_results.extend(self._index_document(doc))
            except Exception:
                logger.exception(
                    "[Skipped] %s (%s) failed and was isolated from the batch.",
                    ref.locator,
                    ref.data_source,
                )
                failed.append(ref.locator)

        self._retire_removed_documents(source, discovered)

        logger.info(
            "[Source Ingest] %s: %d ok, %d failed, %d chunks indexed.",
            source.source_type,
            len(references) - len(failed),
            len(failed),
            len(all_results),
        )
        return all_results, failed

    def _retire_removed_documents(
        self,
        source: DocumentSource,
        discovered: set,
    ) -> None:
        """Marks inactive any active document the source no longer provides.

        Deletion is a liveness flag, not a delete: chunks stay in the
        store with ``is_active=False`` so a re-appearing or re-instated
        document can be restored without re-embedding.
        """
        store = self.stages["store"]
        registry = self.stages["registry"]

        for doc_id, record in list(registry.all().items()):
            if (
                record.get("data_source") == source.source_type
                and record.get("is_active") is True
                and record.get("locator") not in discovered
            ):
                retired = store.deactivate_document(doc_id)
                registry.set_active(doc_id, False)
                logger.info(
                    "[Retired] %s no longer provided by source — deactivated (%d chunks).",
                    doc_id,
                    retired,
                )

    def run_directory(
        self,
        directory: Path,
        patterns: Optional[Tuple[str, ...]] = None,
    ) -> Tuple[List[EmbeddedChunk], List[str]]:
        """Convenience wrapper: scans ``directory`` recursively and ingests
        every matching document via a :class:`FileSystemSource`."""
        return self.ingest_source(
            FileSystemSource(
                directory,
                patterns=patterns or get_settings().sources.patterns,
            )
        )


# =====================================================================
# PIPELINE EXECUTION FOR AETHER WIRELESS
# =====================================================================

def main() -> int:
    """Delegates to the shared CLI entry point (:mod:`ingestion.cli`)."""
    from ingestion.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())