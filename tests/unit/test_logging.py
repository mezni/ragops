import logging

from core.logging import configure_logging


def test_configure_logging_is_idempotent():
    configure_logging(logging.INFO)
    configure_logging(logging.DEBUG)
    configure_logging(logging.INFO)

    root = logging.getLogger()
    ragops_handlers = [
        h for h in root.handlers if h.name == "ragops-console"
    ]
    assert len(ragops_handlers) == 1


def test_configure_logging_pins_package_levels():
    configure_logging(logging.INFO)
    assert logging.getLogger("ingestion").getEffectiveLevel() == logging.INFO
    assert logging.getLogger("core").getEffectiveLevel() == logging.INFO
    assert logging.getLogger("utils").getEffectiveLevel() == logging.INFO
    assert logging.getLogger().getEffectiveLevel() == logging.WARNING