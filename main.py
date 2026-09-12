#!/usr/bin/env python3
"""Root entry point for the RAG pipeline.

Usage:
    python main.py [input_dir] [--query ...] [--top-k N] [--patterns *.pdf ...]

Runs the shared CLI from ``ingestion.cli``. ``src/`` is added to ``sys.path``
so the script also works with a plain (non-``uv run``) interpreter that has
the dependencies installed.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ingestion.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())