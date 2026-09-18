#!/usr/bin/env python3
"""Exports key API responses to data/export/*.json so the dashboard can be hosted statically (GitHub Pages) with
window.UK_ETDI_API_BASE pointing at the export folder (read-only mode)."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "export"
PATHS = {"dashboard/summary": "summary", "dashboard/trends?days=30": "trends", "dashboard/map?days=7": "map", "events?range=7d&page_size=500": "events_7d",
         "events?range=30d&page_size=500": "events_30d", "opportunities?days=7&page_size=500": "opportunities", "actions?days=14&page_size=500": "actions",
         "sources": "sources", "reports/daily": "daily_report", "health/detailed": "health", "changes?days=7": "changes"}
OUT.mkdir(parents=True, exist_ok=True)
with TestClient(app) as c:
    for path, name in PATHS.items():
        (OUT / f"{name}.json").write_text(json.dumps(c.get(f"/api/{path}").json(), default=str))
print(f"exported {len(PATHS)} snapshots to {OUT}")
