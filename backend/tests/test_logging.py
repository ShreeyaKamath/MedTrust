import json
import logging

from backend.app.core.logging import JsonFormatter, configure_logging


def test_json_format_excludes_exception_and_extra():
    record = logging.LogRecord("medtrust.api", logging.ERROR, "", 0, "safe_event", (), None)
    record.exc_info = (RuntimeError, RuntimeError("private-test-marker"), None)
    record.token = "private-test-marker"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "safe_event"
    assert payload["level"] == "ERROR"
    assert payload["timestamp"]
    assert "private-test-marker" not in json.dumps(payload)


def test_configuration_is_idempotent():
    logger = logging.getLogger("medtrust")
    original_handlers, original_level, original_propagate = (
        logger.handlers[:],
        logger.level,
        logger.propagate,
    )
    try:
        configure_logging("WARNING")
        handlers = logger.handlers[:]
        configure_logging("ERROR")
        assert logger.handlers == handlers
        assert logger.level == logging.ERROR
        assert logger.propagate is False
    finally:
        for handler in logger.handlers:
            if handler not in original_handlers:
                handler.close()
        logger.handlers = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate
