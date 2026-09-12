import hashlib
import logging
import re
from typing import List, Optional, Tuple

from core.config import get_settings
from ingestion.schemas import ChunkMetadata, Document, TextChunk

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
        """Splits document text into natural chunks, then builds structured
        :class:`ChunkMetadata` for each slice.

        Every chunk inherits the document-level metadata (tenant_id,
        department, status, classification, ...) so vector-store pre-filters
        like ``where={"tenant_id": ..., "status": "active"}`` apply to each
        slice. Chunk-local fields (chunk_index, total_chunks, char offsets,
        content_hash, header_path breadcrumb) are layered on top. A 1-sentence
        chunk ``summary`` is reserved for an LLM enrichment stage.
        """
        splits = self._split_text(doc.content, self.separators)
        doc_md = doc.metadata

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
                    metadata=ChunkMetadata(
                        doc_id=doc.doc_id,
                        source_path=doc_md.source_path,
                        source=doc.source,
                        file_name=doc_md.file_name,
                        file_type=doc_md.file_type,
                        data_source=doc_md.data_source,
                        content_hash=hashlib.sha256(
                            chunk_text.encode("utf-8")
                        ).hexdigest(),
                        char_start=start,
                        char_end=end,
                        page_number=None,  # filled by PDF-aware splitting/enrichment
                        chunk_index=chunk_idx,
                        total_chunks=len(splits),
                        header_path=self._breadcrumb(doc.content, start),
                        summary=None,  # reserved for LLM enrichment stage
                        tenant_id=doc_md.tenant_id,
                        access_roles=list(doc_md.access_roles),
                        classification=doc_md.classification,
                        category=doc_md.category,
                        department=doc_md.department,
                        doc_type=doc_md.doc_type,
                        domain=doc_md.domain,
                        language=doc_md.language,
                        status=doc_md.status,
                        doc_version=doc_md.doc_version,
                        last_updated=doc_md.updated_at,
                    ),
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Section hierarchy (breadcrumb) reconstruction
    # ------------------------------------------------------------------

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
    _SECTION_RE = re.compile(r"^(\d+(?:\.\d+){0,3})[\.\)]?\s+(.+)$")
    _MAX_BREADCRUMB_DEPTH = 4

    @classmethod
    def _heading(cls, line: str) -> Optional[str]:
        """Normalizes one line into a breadcrumb segment, or None."""
        s = line.strip()
        m = cls._HEADING_RE.match(s)
        if m:
            return m.group(2).strip()
        m = cls._SECTION_RE.match(s)
        if m:
            return f"{m.group(1)} {m.group(2).strip()}"
        return None

    def _breadcrumb(self, content: str, chunk_start: int) -> str:
        """Reconstructs the section hierarchy above ``chunk_start``.

        Walks the text before the chunk, collecting heading / numbered
        section lines (e.g. "# Refunds", "1.2 Exceptions") into a "Parent >
        Child > Leaf" path, bounded to the most recent headings.
        """
        path: List[str] = []
        for line in content[:chunk_start].splitlines():
            heading = self._heading(line)
            if heading is None:
                continue
            path.append(heading)
            if len(path) > self._MAX_BREADCRUMB_DEPTH:
                path.pop(0)
        return " > ".join(path[-self._MAX_BREADCRUMB_DEPTH:])

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