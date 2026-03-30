"""Structured JSON logging for all workers and services."""
import json
import logging
import traceback
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = traceback.format_exception(*record.exc_info)[-1].strip()
        return json.dumps(log, ensure_ascii=False)


def setup(level: str = "INFO") -> None:
    """Configure root logger with JSON output."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Suppress noisy third-party loggers
    for name in ("sqlalchemy.engine", "sqlalchemy.pool", "urllib3", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)
