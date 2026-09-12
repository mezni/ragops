import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
import numpy as np
import pypdf
from bs4 import BeautifulSoup


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
# 2. INDEXING PIPELINE
# =====================================================================

class RAGIndexingPipeline:
    """Class-based pipeline that executes document loading, chunking, and indexing."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
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
        self.vector_store: Dict[str, EmbeddedChunk] = {}

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

    def load_file(self, file_path: Path) -> Document:
        """Reads a .pdf or .txt file from disk, cleans content, and constructs a Document model."""
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
                **extracted_meta,  # Saved into Chroma payload rather than chunk text
            }
        )

    def chunk_document(self, doc: Document) -> List[TextChunk]:
        """Splits document text into overlapping chunks and maps back metadata."""
        chunks: List[TextChunk] = []
        text = doc.content
        start = 0
        chunk_idx = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]

            chunk = TextChunk(
                chunk_id=f"{doc.doc_id}_chunk_{chunk_idx}",
                doc_id=doc.doc_id,
                text=chunk_text,
                chunk_index=chunk_idx,
                metadata={
                    **doc.metadata,
                    "source": doc.source,
                    "char_start": start,
                    "char_end": min(end, len(text))
                }
            )
            chunks.append(chunk)

            start += self.chunk_size - self.chunk_overlap
            chunk_idx += 1

        return chunks

    def generate_embeddings(self, chunks: List[TextChunk]) -> List[EmbeddedChunk]:
        """Generates vector embeddings for text chunks (1536-dim dummy vectors for baseline)."""
        embedded_chunks: List[EmbeddedChunk] = []

        for chunk in chunks:
            # Mock 1536-dimensional embedding (Replace with OpenAI/SentenceTransformers in Step 2)
            mock_embedding = np.random.uniform(-1, 1, 1536).tolist()

            embedded_chunks.append(EmbeddedChunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                text=chunk.text,
                embedding=mock_embedding,
                metadata=chunk.metadata
            ))

        return embedded_chunks

    def upsert_to_vector_store(self, embedded_chunks: List[EmbeddedChunk]) -> int:
        """Stores embedded chunks into the in-memory vector store."""
        for item in embedded_chunks:
            self.vector_store[item.chunk_id] = item
        return len(embedded_chunks)

    def run(self, file_path: Path) -> List[EmbeddedChunk]:
        """Executes full ingestion flow for a single target file."""
        doc = self.load_file(file_path)
        chunks = self.chunk_document(doc)
        embedded_chunks = self.generate_embeddings(chunks)
        count = self.upsert_to_vector_store(embedded_chunks)
        print(f"[Pipeline Success] Indexed {count} chunks from: {file_path.name}")
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

        # Inspect the first chunk extracted from the PDF
        print("\n--- First Chunk Extracted from PDF ---")
        print(f"Chunk ID: {results[0].chunk_id}")
        print(f"Category: {results[0].metadata.get('category')}")
        print(f"Text snippet:\n{results[0].text[:200]!r}...")
    except FileNotFoundError:
        print(f"[Error] File not found at {target_pdf}. Please ensure the PDF is placed in the sub-folder.")