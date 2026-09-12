import logging
from pathlib import Path
from typing import List, Tuple, Union

from ingestion.schemas import SourceReference
from ingestion.sources.base import DocumentSource

logger = logging.getLogger(__name__)


class FileSystemSource(DocumentSource):
    """Recursively discovers documents under a directory tree.

    Files directly inside ``root_dir`` get ``category`` = the folder name;
    each sub-directory becomes its own category (e.g. ``billing``,
    ``billing/escalation``). Extensions can be restricted via ``patterns``.
    """

    source_type = "filesystem"

    DEFAULT_PATTERNS: Tuple[str, ...] = ("*.pdf", "*.txt", "*.md")

    def __init__(
        self,
        root_dir: Union[Path, str],
        patterns: Tuple[str, ...] = DEFAULT_PATTERNS,
    ):
        self.root_dir = Path(root_dir)
        self.patterns = patterns or self.DEFAULT_PATTERNS

    def discover(self) -> List[SourceReference]:
        if not self.root_dir.is_dir():
            raise FileNotFoundError(f"Input directory not found: {self.root_dir}")

        references: List[SourceReference] = []

        for pattern in self.patterns:
            for path in sorted(self.root_dir.rglob(pattern)):
                if not path.is_file():
                    continue
                references.append(
                    SourceReference(
                        locator=str(path),
                        doc_id=path.stem,
                        category=path.parent.name,
                        file_name=path.name,
                        file_type=path.suffix.lower(),
                        data_source=self.source_type,
                    )
                )

        logger.info(
            "[Discover] filesystem scanned %s: %d files",
            self.root_dir,
            len(references),
        )
        return references