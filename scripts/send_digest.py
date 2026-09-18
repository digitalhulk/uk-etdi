#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.db.database import init_db, session_scope  # noqa: E402
from app.notifications.telegram import send_message  # noqa: E402
from app.orchestration.reports import build_daily_report, format_daily_digest  # noqa: E402
init_db()
with session_scope() as db:
    text = format_daily_digest(build_daily_report(db))
print(text); print(send_message(text))
