"""JSON application logs. Use fixed event messages, never request or secret data.

Only the medtrust logger is configured; server/access logs are managed separately.
Exception text, tracebacks and arbitrary extra fields are deliberately omitted.
"""

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        )


def configure_logging(level: str = "INFO") -> None:
    """Configure a dedicated logger idempotently without changing root handlers."""
    logger = logging.getLogger("medtrust")
    if not any(getattr(handler, "_medtrust_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._medtrust_handler = True
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
