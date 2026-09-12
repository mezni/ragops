import os
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key-for-unit-tests")

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = REPO_ROOT / "data" / "raw"