"""Optional Google Sheets output via an Apps Script web-app webhook (free). Batch POST; failures never stop the pipeline."""
from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("sheets")


def push_report(report: dict) -> tuple[bool, str]:
    url = get_settings().google_sheets_webhook
    if not url:
        return False, "not_configured"
    try:
        r = httpx.post(url, json={"sheets": {"Daily Reports": [report["summary"]], "Opportunities": report["top_opportunities"], "Events": report["today"]}}, timeout=20)
        return (r.status_code < 300), f"status {r.status_code}"
    except Exception as exc:
        log.warning("sheets push failed: %s", exc)
        return False, str(exc)[:200]
