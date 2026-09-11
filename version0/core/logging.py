import logging
import sys
import structlog
from core.config import settings


def setup_logging() -> None:
    """Configures structured logging for the RAG pipeline."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Shared processors applied to all log messages
    shared_processors = [
        structlog.contextvars.merge_contextvars,          # Pull bound thread/async context
        structlog.stdlib.add_logger_name,                  # Include logger name
        structlog.stdlib.add_log_level,                     # Include log level (info, error)
        structlog.stdlib.PositionalArgumentsFormatter(),   # Support % formatting like standard logging
        structlog.processors.TimeStamper(fmt="iso"),        # Standardized ISO timestamps
        structlog.processors.StackInfoRenderer(),          # Format stack traces
        structlog.processors.format_exc_info,              # Format exception traces
    ]

    # Render as JSON for production, or clean console print for local dev
    if settings.JSON_LOGS:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # Configure Structlog entry point
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Wrap standard Python logging output so third-party logs pass through Structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Direct logs to standard output (sys.stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # Remove standard handlers to prevent duplication
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Retrieves a named structured logger instance."""
    return structlog.get_logger(name)