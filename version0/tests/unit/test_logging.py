import json
import re
from types import SimpleNamespace

import core.logging as logging_module

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def test_json_logs_emit_valid_json(capsys):
    logging_module.settings = SimpleNamespace(LOG_LEVEL="INFO", JSON_LOGS=True)
    logging_module.setup_logging()

    logger = logging_module.get_logger("tests")
    logger.info("pipeline_started", stage="ingest", documents=42)

    out = capsys.readouterr().out
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["event"] == "pipeline_started"
    assert payload["level"] == "info"
    assert payload["stage"] == "ingest"
    assert payload["documents"] == 42
    assert payload["logger"] == "tests"


def test_console_logs_when_json_disabled(capsys):
    logging_module.settings = SimpleNamespace(LOG_LEVEL="INFO", JSON_LOGS=False)
    logging_module.setup_logging()

    logger = logging_module.get_logger("tests")
    logger.warning("low_embedding_score", score=0.4)

    out = ANSI.sub("", capsys.readouterr().out)
    assert "low_embedding_score" in out
    assert "score=0.4" in out