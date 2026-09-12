import logging
from typing import List, Optional, Tuple

from core.config import get_settings
from ingestion.schemas import Document, TextChunk

logger = logging.getLogger(__name__)

_settings = get_settings()


class Chunker:
    """Splits a Document into overlapping TextChunks.

    Uses recursive structure-aware splitting: text is broken along a
    hierarchy of natural boundaries — paragraphs ("\\n\\n"), lines ("\\n"),
    sentences (". "), spaces (" ") — before ever resorting to arbitrary
    character cuts. Each chunk stays within ``chunk_size`` and carries a
    window of ``chunk_overlap`` from the previous chunk.
    """

    # Hierarchy of separators, from most to least natural (see config).
    DEFAULT_SEPARATORS: Tuple[str, ...] = _settings.chunking.separators

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        separators: Optional[Tuple[str, ...]] = None,
    ):
        cfg = _settings.chunking
        chunk_size = chunk_size if chunk_size is not None else cfg.chunk_size
        chunk_overlap = (
            chunk_overlap if chunk_overlap is not None else cfg.chunk_overlap
        )
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
        """Splits document text into natural chunks and maps back metadata.

        Every chunk inherits the full document-level metadata (tenant_id,
        department, status, classification, ...) so vector-store pre-filters
        like ``where={"tenant_id": ..., "status": "active"}`` apply to each
        slice. Chunk-local keys (chunk_index, char offsets, total_chunks)
        are layered on top.
        """
        splits = self._split_text(doc.content, self.separators)

        chunks: List[TextChunk] = []
        search_from = 0
        doc_metadata = doc.metadata.model_dump()

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
                        **doc_metadata,
                        "source": doc.source,
                        "chunk_index": chunk_idx,
                        "total_chunks": len(splits),
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

    def _hard_split(self, text: str) -> List[str]:
        """Fallback: split a single oversized block into fixed-size pieces."""
        if len(text) <= self.chunk_size:
            return [text]

        pieces: List[str] = []
        for i in range(0, len(text), self.chunk_size):
            pieces.append(text[i:i + self.chunk_size])
        return pieces


# Backward-compatible alias (legacy name from the single-file stage refactor)
ChunkerStage = Chunker