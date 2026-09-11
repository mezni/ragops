from pathlib import Path
from typing import List, Optional, Set
import mimetypes

from core.hash import compute_file_hash
from core.logging import get_logger
from loaders.base import BaseSourceLoader, RawPayload

logger = get_logger(__name__)


class FilesystemLoader(BaseSourceLoader):
    """Scans local directories and loads file contents into RawPayload objects."""

    def __init__(
        self,
        directory_path: str,
        allowed_extensions: Optional[Set[str]] = None,
        recursive: bool = True
    ):
        self.directory_path = Path(directory_path)
        self.allowed_extensions = allowed_extensions or {".txt", ".md", ".pdf", ".json", ".csv"}
        self.recursive = recursive

    def load(self) -> List[RawPayload]:
        if not self.directory_path.exists():
            logger.error("Directory path does not exist", path=str(self.directory_path))
            raise FileNotFoundError(f"Directory not found: {self.directory_path}")

        pattern = "**/*" if self.recursive else "*"
        payloads: List[RawPayload] = []

        for file_path in self.directory_path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.allowed_extensions:
                try:
                    mime_type, _ = mimetypes.guess_type(file_path)
                    content_type = mime_type or "text/plain"

                    # For text-based formats, read text directly
                    # PDFs or binaries can be loaded as text-encoded or raw paths for specialized parsers
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        # Fallback for binary files like PDFs - store absolute path for specialized parser
                        content = str(file_path.resolve())

                    file_stat = file_path.stat()
                    canonical_id = str(file_path.resolve())

                    payload = RawPayload(
                        payload_id=canonical_id,
                        source_type="filesystem",
                        source_uri=canonical_id,
                        raw_content=content,
                        content_type=content_type,
                        metadata={
                            "filename": file_path.name,
                            "file_extension": file_path.suffix,
                            "file_size_bytes": file_stat.st_size,
                            "file_hash": compute_file_hash(file_path),
                        }
                    )
                    payloads.append(payload)
                except Exception as e:
                    logger.warning("Failed to load file", file_path=str(file_path), error=str(e))

        logger.info("Filesystem loading completed", total_loaded=len(payloads))
        return payloads