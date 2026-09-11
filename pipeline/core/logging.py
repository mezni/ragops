"""Structured single-line JSON logging (Constitution-pattern CLI tooling)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_ROOT_LOGGER_NAME = "pipeline"


class JsonFormatter(logging.Formatter):
    """Emit one compact JSON object per log record on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", name: str = _ROOT_LOGGER_NAME) -> logging.Logger:
    """Attach a JSON handler to a logger.

    Idempotent: repeated calls do not stack duplicate handlers.
    Output goes to ``stderr`` (results on stdout, errors on stderr).
    """
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger