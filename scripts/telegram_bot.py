#!/usr/bin/env python3
"""Long-polling Telegram bot runner (zero-cost; run locally, on a free tier, or as a short GitHub Actions job)."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import httpx  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.notifications.telegram import handle_command, send_message  # noqa: E402

s = get_settings()
if not s.telegram_bot_token:
    sys.exit("TELEGRAM_BOT_TOKEN not set")
init_db()
offset = None
max_seconds = int(os.getenv("BOT_MAX_SECONDS", "0"))  # 0 = forever
start = time.time()
while not max_seconds or time.time() - start < max_seconds:
    r = httpx.get(f"https://api.telegram.org/bot{s.telegram_bot_token}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=40)
    for u in r.json().get("result", []):
        offset = u["update_id"] + 1
        msg = u.get("message") or {}
        if msg.get("text", "").startswith("/"):
            with session_scope() as db:
                send_message(handle_command(db, msg["text"]), chat_id=str(msg["chat"]["id"]))
