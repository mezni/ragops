import hashlib
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field
import pypdf
from bs4 import BeautifulSoup
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent / ".env")


# =====================================================================
# 1. PYDANTIC SCHEMAS
# =====================================================================

class Document(BaseModel):
    """Raw document extracted from disk before chunking."""
    doc_id: str = Field(..., description="Unique identifier (e.g., file name)")
    content: str = Field(..., min_length=1, description="Extracted raw text")
    source: str = Field(..., description="Absolute or relative file path")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata")


class TextChunk(BaseModel):
    """Processed text chunk ready for embedding."""
    chunk_id: str = Field(..., description="Unique identifier (doc_id_chunk_N)")
    doc_id: str = Field(..., description="Parent document ID")
    text: str = Field(..., min_length=1, description="Chunked text slice")
    chunk_index: int = Field(..., ge=0, description="Sequential index")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Merged metadata")


class EmbeddedChunk(BaseModel):
    """Vectorized chunk ready for database insertion."""
    chunk_id: str
    doc_id: str
    text: str
    embedding: List[float] = Field(..., description="Dense vector embedding")
    metadata: Dict[str, Any]


# =====================================================================
# 2. PIPELINE STAGES
# =====================================================================

class IngestionStage:
    """Loads raw files, strips HTML/markup, and extracts administrative
    frontmatter into metadata. Output: Document."""

    @staticmethod
    def clean_text(raw_text: str) -> str:
        """Removes HTML tags and normalizes whitespace."""
        # 1. Strip HTML tags like <b>, </b>
        soup = BeautifulSoup(raw_text, "html.parser")
        cleaned = soup.get_text(separator=" ")

        # 2. Normalize multiple spaces and extra newlines
        cleaned = re.sub(r"\n+", "\n", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def extract_frontmatter(text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Extracts key-value header metadata (e.g., Version, Last Updated, Status)
        and strips it from the main body content.
        """
        extracted_meta = {}

        # Regex patterns to capture administrative header blocks
        patterns = {
            "document_id": r"Document ID\s*:\s*([A-Z0-9-]+)",
            "version": r"Version\s*:\s*([\d.]+)",
            "department": r"Department\s*:\s*([A-Za-z]+)",
            "last_updated": r"Last Updated\s*:\s*([\d-]+)",
            "status": r"Status\s*:\s*([A-Za-z]+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_meta[key] = match.group(1).strip()
                # Remove matched key-value string from core text
                text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        return text.strip(), extracted_meta

    def run(self, file_path: Path) -> Document:
        """Reads a .pdf or .txt file, cleans content, and constructs a Document."""
        if not file_path.exists():
            raise FileNotFoundError(f"Target document not found: {file_path}")

        raw_text = ""
        # 1. Extract raw text from file
        if file_path.suffix.lower() == ".pdf":
            reader = pypdf.PdfReader(file_path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    raw_text += page_text + "\n"
        elif file_path.suffix.lower() in [".txt", ".md"]:
            raw_text = file_path.read_text(encoding="utf-8")
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

        if not raw_text.strip():
            raise ValueError(f"Extracted content is empty for file: {file_path}")

        # Content digest to power idempotent deduplication downstream
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        # 2. Clean HTML & extract administrative frontmatter
        sanitized_text = self.clean_text(raw_text)
        body_text, extracted_meta = self.extract_frontmatter(sanitized_text)

        return Document(
            doc_id=file_path.stem,
            content=body_text,
            source=str(file_path),
            metadata={
                "file_name": file_path.name,
                "file_type": file_path.suffix.lower(),
                "category": file_path.parent.name,  # Captures "billing" from path
                "content_hash": content_hash,
                **extracted_meta,  # Saved into Chroma payload rather than chunk text
            }
        )


class ChunkerStage:
    """Splits a Document into overlapping TextChunks.

    Uses recursive structure-aware splitting: text is broken along a
    hierarchy of natural boundaries — paragraphs ("\\n\\n"), lines ("\\n"),
    sentences (". "), spaces (" ") — before ever resorting to arbitrary
    character cuts. Each chunk stays within ``chunk_size`` and carries a
    window of ``chunk_overlap`` from the previous chunk.
    """

    # Hierarchy of separators, from most to least natural.
    DEFAULT_SEPARATORS: Tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: Optional[Tuple[str, ...]] = None,
    ):
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be < chunk_size ({chunk_size})"
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS

    def run(self, doc: Document) -> List[TextChunk]:
        """Splits document text into natural chunks and maps back metadata."""
        splits = self._split_text(doc.content, self.separators)

        chunks: List[TextChunk] = []
        search_from = 0

        for chunk_idx, chunk_text in enumerate(splits):
            # Locate the chunk inside the original text for offset metadata.
            start = doc.content.find(chunk_text, search_from)
            if start == -1:
                start = 0
            end = start + len(chunk_text)
            search_from = start + 1

            chunks.append(
                TextChunk(
                    chunk_id=f"{doc.doc_id}_chunk_{chunk_idx}",
                    doc_id=doc.doc_id,
                    text=chunk_text,
                    chunk_index=chunk_idx,
                    metadata={
                        **doc.metadata,
                        "source": doc.source,
                        "char_start": start,
                        "char_end": end,
                    }
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Recursive splitting primitives
    # ------------------------------------------------------------------

    def _split_text(
        self,
        text: str,
        separators: Tuple[str, ...],
    ) -> List[str]:
        """Recursively split text, preferring the largest suitable separator."""
        final_chunks: List[str] = []

        separator = separators[-1]
        new_separators: Tuple[str, ...] = ()

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break

        splits = text.split(separator) if separator else list(text)

        good_splits: List[str] = []

        for part in splits:
            if len(part) < self.chunk_size:
                good_splits.append(part)
            else:
                if good_splits:
                    final_chunks.extend(self._merge_splits(good_splits, separator))
                    good_splits = []

                if not new_separators:
                    # Deepest level — fall back to fixed-size overlapping cuts.
                    final_chunks.extend(self._hard_split(part))
                else:
                    final_chunks.extend(self._split_text(part, new_separators))

        if good_splits:
            final_chunks.extend(self._merge_splits(good_splits, separator))

        return final_chunks

    def _merge_splits(
        self,
        splits: List[str],
        separator: str,
    ) -> List[str]:
        """Group small splits into chunks near ``chunk_size`` with overlap."""
        docs: List[str] = []
        current_doc: List[str] = []
        total = 0
        sep_len = len(separator)

        for part in splits:
            part_len = len(part)

            # Would adding this piece exceed the target size?
            overflow = total + part_len + (sep_len if current_doc else 0)

            if overflow > self.chunk_size:
                if current_doc:
                    joined = self._join_docs(current_doc, separator)
                    if joined is not None:
                        docs.append(joined)

                    # Trim from the front while the window exceeds overlap.
                    while total > self.chunk_overlap and len(current_doc) > 1:
                        total -= len(current_doc[0]) + sep_len
                        current_doc = current_doc[1:]

            current_doc.append(part)
            total += part_len + (sep_len if len(current_doc) > 1 else 0)

        joined = self._join_docs(current_doc, separator)
        if joined is not None:
            docs.append(joined)

        return docs

    @staticmethod
    def _join_docs(
        docs: List[str],
        separator: str,
    ) -> Optional[str]:
        text = separator.join(docs).strip()
        if not text:
            return None
        return text

    @staticmethod
    def _hard_split(text: str) -> List[str]:
        """Fallback: split a single oversized block into fixed-size pieces."""
        if len(text) <= 500:
            return [text]

        pieces: List[str] = []
        for i in range(0, len(text), 500):
            pieces.append(text[i:i + 500])
        return pieces


class EmbeddingStage:
    """Generates real vector embeddings for TextChunks via OpenRouter."""

    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    def run(
        self,
        chunks: List[TextChunk],
        batch_size: int = 32,
    ) -> List[EmbeddedChunk]:
        """Generates real vector embeddings in batches using OpenRouter."""
        if not chunks:
            return []

        embedded_chunks: List[EmbeddedChunk] = []

        # Process chunks in batches to optimize network efficiency
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text for c in batch]

            # Call OpenRouter embedding endpoint
            response = self.client.embeddings.create(
                model=self.model,
                input=texts
            )

            # Map embeddings back to corresponding chunks
            for chunk, data in zip(batch, response.data):
                embedded_chunks.append(
                    EmbeddedChunk(
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        text=chunk.text,
                        embedding=data.embedding,
                        metadata=chunk.metadata
                    )
                )

        return embedded_chunks


class VectorStoreStage:
    """Persistent ChromaDB vector store. Survives process restarts."""

    def __init__(
        self,
        persist_dir: str = "data/processed/chroma",
        collection_name: str = "aether_wireless_docs",
    ):
        chroma_dir = Path(persist_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self.collection.count()

    def upsert(self, embedded_chunks: List[EmbeddedChunk]) -> int:
        """Persists embedded chunks into the ChromaDB vector store on disk."""
        if not embedded_chunks:
            return 0

        self.collection.upsert(
            ids=[c.chunk_id for c in embedded_chunks],
            embeddings=[c.embedding for c in embedded_chunks],
            documents=[c.text for c in embedded_chunks],
            metadatas=[
                {**c.metadata, "doc_id": c.doc_id} for c in embedded_chunks
            ],
        )
        return len(embedded_chunks)

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Returns top-K context blocks from the persistent store."""
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

    def get_document_hashes(self, doc_id: str) -> Set[str]:
        """Returns the set of content hashes currently stored for a doc_id."""
        result = self.collection.get(
            where={"doc_id": doc_id},
            include=["metadatas"],
        )

        hashes: Set[str] = set()
        for metadata in result.get("metadatas", []) or []:
            content_hash = metadata.get("content_hash")
            if content_hash:
                hashes.add(content_hash)
        return hashes

    def delete_document(self, doc_id: str) -> int:
        """Deletes every chunk belonging to a doc_id. Returns chunks removed."""
        result = self.collection.get(where={"doc_id": doc_id})
        ids = result.get("ids", []) or []

        if ids:
            self.collection.delete(ids=ids)

        return len(ids)


# =====================================================================
# 3. PIPELINE ORCHESTRATOR
# =====================================================================

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
            "loader": IngestionStage(),
            "chunker": ChunkerStage(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
            "embedder": EmbeddingStage(
                client=self.client,
                model=self.OPENROUTER_EMBEDDING_MODEL,
            ),
            "store": VectorStoreStage(
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
        query_embedding = self.client.embeddings.create(
            model=self.OPENROUTER_EMBEDDING_MODEL,
            input=[query_text],
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
            print(f"[Skipped] {doc.doc_id} unchanged (hash {content_hash[:8]}...) — already indexed.")
            return []

        if existing_hashes:
            removed = self.stages["store"].delete_document(doc.doc_id)
            print(f"[Purge] Removed {removed} stale chunks for '{doc.doc_id}' (content changed).")

        chunks = self.stages["chunker"].run(doc)
        embedded_chunks = self.stages["embedder"].run(chunks)
        count = self.stages["store"].upsert(embedded_chunks)
        total = self.stages["store"].count
        print(f"[Pipeline Success] Indexed {count} chunks from: {file_path.name}")
        print(f"[Persist] ChromaDB collection '{self.collection.name}' now holds {total} chunks")
        return embedded_chunks


# =====================================================================
# PIPELINE EXECUTION FOR AETHER WIRELESS
# =====================================================================

if __name__ == "__main__":
    # Define relative path to the requested PDF document
    target_pdf = Path("data/raw/billing/AW-BIL-001_billing_dispute_policy.pdf")

    # Initialize and execute pipeline
    pipeline = RAGIndexingPipeline(chunk_size=500, chunk_overlap=50)

    try:
        results = pipeline.run(target_pdf)

        if results:
            # Inspect the first chunk extracted from the PDF
            print("\n--- First Chunk Extracted from PDF ---")
            print(f"Chunk ID: {results[0].chunk_id}")
            print(f"Category: {results[0].metadata.get('category')}")
            print(f"Text snippet:\n{results[0].text[:200]!r}...")

        # Sanity check: query the persistent store it was just written to
        print("\n--- Sanity Search ---")
        hits = pipeline.search("how long does a billing dispute investigation take?")
        ids = hits.get("ids", [[]])[0]
        print(f"Top-K hit ids: {ids[:3]}")
    except FileNotFoundError:
        print(f"[Error] File not found at {target_pdf}. Please ensure the PDF is placed in the sub-folder.")