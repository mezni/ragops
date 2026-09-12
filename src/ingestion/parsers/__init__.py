"""Format parsers: one parser per document format.

The loader delegates extraction to the parser matching a file's
extension through :func:`get_parser`. Add a new format by implementing
``DocumentParser`` with the relevant ``extensions`` and registering it.
"""

from pathlib import Path
from typing import List, Tuple, Union

from ingestion.parsers.base import DocumentParser
from ingestion.parsers.markdown import MarkdownParser
from ingestion.parsers.pdf import PDFParser
from ingestion.parsers.text import TextParser

# Default registered parsers, in priority order.
DEFAULT_PARSERS: Tuple[DocumentParser, ...] = (
    PDFParser(),
    MarkdownParser(),
    TextParser(),
)


def get_parser(
    path: Union[Path, str],
    parsers: Tuple[DocumentParser, ...] = DEFAULT_PARSERS,
) -> DocumentParser:
    """Returns the parser registered for ``path``'s extension.

    Raises ``ValueError`` when no parser handles the format.
    """
    extension = Path(path).suffix.lower()
    for parser in parsers:
        if extension in parser.extensions:
            return parser
    raise ValueError(f"Unsupported file format: {extension}")


def supported_extensions(parsers: Tuple[DocumentParser, ...] = DEFAULT_PARSERS) -> List[str]:
    """Returns every extension handled by the registered parsers."""
    return [ext for parser in parsers for ext in parser.extensions]


__all__ = [
    "DEFAULT_PARSERS",
    "DocumentParser",
    "MarkdownParser",
    "PDFParser",
    "TextParser",
    "get_parser",
    "supported_extensions",
]