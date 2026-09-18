"""In-process scheduler (optional). Primary scheduling is GitHub Actions cron; this covers self-hosted mode.
Enable with SCHEDULER_ENABLED=1; interval via SCHEDULER_INTERVAL_MINUTES (default 1440 = daily)."""
from __future__ import annotations

import os
import threading
import time

from app.core.logging import get_logger

log = get_logger("scheduler")
_thread: threading.Thread | None = None
_stop = threading.Event()


def _loop(interval_min: int) -> None:
    from app.orchestration.jobs import job_pipeline
    while not _stop.is_set():
        try:
            job_pipeline(trigger="scheduled")
        except Exception:
            log.exception("scheduled pipeline failed")
        _stop.wait(interval_min * 60)


def start_scheduler() -> bool:
    global _thread
    if os.getenv("SCHEDULER_ENABLED", "0") != "1" or _thread:
        return False
    interval = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "1440"))
    _thread = threading.Thread(target=_loop, args=(interval,), daemon=True, name="uk-etdi-scheduler")
    _thread.start()
    log.info("scheduler started (every %s min)", interval)
    return True


def stop_scheduler() -> None:
    _stop.set()
