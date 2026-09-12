import logging


_console_handler_name = "ragops-console"


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent production logging: structured, timestamped stderr logs.

    Attaches a single named console handler to the root logger while
    pinning our own package loggers ("ingestion", "core", "utils") to
    ``level``. Safe to call repeatedly.
    """
    root = logging.getLogger()

    if not any(
        h.name == _console_handler_name for h in root.handlers
    ):
        handler = logging.StreamHandler()
        handler.name = _console_handler_name
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(handler)

    root.setLevel(logging.WARNING)
    for pkg in ("ingestion", "core", "utils"):
        logging.getLogger(pkg).setLevel(level)