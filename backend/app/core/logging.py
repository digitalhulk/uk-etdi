"""Logging: human-readable console + structured JSON events (LOG_FORMAT=json switches the whole stream to JSON)."""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

from .config import get_settings

_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        if hasattr(record, "structured"):
            base.update(record.structured)  # type: ignore[attr-defined]
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)[-800:]
        return json.dumps(base, default=str)


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("LOG_FORMAT", "text").lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, *, run_id=None, source=None, stage=None, status=None, duration_ms=None, level=logging.INFO, **extra) -> None:
    """Structured event: {"run_id","source","stage","status","duration_ms",...}"""
    payload = {"run_id": run_id, "source": source, "stage": stage, "status": status, "duration_ms": duration_ms, **extra}
    payload = {k: v for k, v in payload.items() if v is not None}
    logger.log(level, " ".join(f"{k}={v}" for k, v in payload.items()), extra={"structured": payload})
