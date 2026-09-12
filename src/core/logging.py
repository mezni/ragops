import logging
from typing import Optional

from core.config import get_settings


def configure_logging(level: Optional[int] = None) -> None:
    """Idempotent production logging: structured, timestamped stderr logs.

    Attaches a single named console handler to the root logger while
    pinning our own package loggers ("ingestion", "core", "utils") to the
    package level. Safe to call repeatedly. Settings come from
    :mod:`core.config`; ``level`` overrides ``logging.level`` if given.
    """
    cfg = get_settings().logging
    if level is None:
        level = cfg.level

    root = logging.getLogger()

    if not any(
        h.name == cfg.console_handler_name for h in root.handlers
    ):
        handler = logging.StreamHandler()
        handler.name = cfg.console_handler_name
        handler.setFormatter(
            logging.Formatter(
                cfg.format,
                datefmt=cfg.datefmt,
            )
        )
        root.addHandler(handler)

    root.setLevel(cfg.root_level)
    for pkg in cfg.package_loggers:
        logging.getLogger(pkg).setLevel(level)