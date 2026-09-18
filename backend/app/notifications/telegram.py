"""Telegram bot: daily push + command handling (long-polling runner in scripts/telegram_bot.py)."""
from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("telegram")


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{get_settings().telegram_bot_token}/{method}"


def is_configured() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_chat_id)


def send_message(text: str, chat_id: str | None = None) -> tuple[bool, str]:
    s = get_settings()
    if not s.telegram_bot_token or not (chat_id or s.telegram_chat_id):
        return False, "not_configured"
    try:
        r = httpx.post(_api("sendMessage"), json={"chat_id": chat_id or s.telegram_chat_id, "text": text[:4000], "disable_web_page_preview": True}, timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            return True, "sent"
        return False, f"telegram error {r.status_code}: {r.text[:200]}"
    except Exception as exc:
        log.warning("telegram send failed: %s", exc)
        return False, str(exc)[:200]


def handle_command(db, text: str) -> str:
    """Maps bot commands to database queries. Used by the polling runner and unit-tested directly."""
    from datetime import date, timedelta

    from sqlalchemy import select

    from app.db.models import Event, PipelineRun
    from app.orchestration.reports import build_daily_report, format_daily_digest

    cmd = text.strip().split()[0].lower().split("@")[0] if text.strip() else ""
    today = date.today()
    active = Event.status.in_(("SCHEDULED", "RESCHEDULED"))

    def listing(title: str, conds, limit: int = 10) -> str:
        rows = db.scalars(select(Event).where(active, *conds).order_by(Event.opportunity_score.desc()).limit(limit)).all()
        if not rows:
            return f"{title}\n\nNo events found."
        lines = [title, ""]
        for e in rows:
            lines.append(f"• {e.title} — {e.city.name if e.city else e.city_name_raw or '?'} {e.date_start.strftime('%d %b')} {e.time_start or 'TBC'} — 🔥{e.opportunity_score} {e.demand_level}")
        return "\n".join(lines)

    if cmd == "/start":
        return "🚕 UK-ETDI bot ready.\n/today /tomorrow /week /high /concerts /sports /education /status"
    if cmd == "/today":
        return listing("📅 TODAY", [Event.date_start == today])
    if cmd == "/tomorrow":
        return listing("📅 TOMORROW", [Event.date_start == today + timedelta(days=1)])
    if cmd == "/week":
        return listing("📅 NEXT 7 DAYS (top)", [Event.date_start >= today, Event.date_start <= today + timedelta(days=7)])
    if cmd == "/high":
        return listing("🔥 HIGH / VERY HIGH", [Event.date_start >= today, Event.demand_level.in_(("HIGH", "VERY_HIGH"))])
    if cmd == "/concerts":
        return listing("🎵 CONCERTS", [Event.date_start >= today, Event.category == "music"])
    if cmd == "/sports":
        return listing("⚽ SPORTS", [Event.date_start >= today, Event.category == "sports"])
    if cmd == "/education":
        return listing("🎓 EDUCATION", [Event.date_start >= today, Event.category == "education"])
    if cmd == "/status":
        run = db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)).first()
        if not run:
            return "No pipeline runs yet."
        return (f"⚙️ Last run #{run.id}: {run.status}\nStarted {run.started_at:%Y-%m-%d %H:%M} UTC, {run.duration_seconds}s\n"
                f"Sources ok/failed: {run.sources_successful}/{run.sources_failed}\nRaw {run.events_raw} · valid {run.events_valid} · new {run.events_created} · "
                f"updated {run.events_updated} · dupes {run.duplicates_removed} · changes {run.changes_detected}")
    if cmd == "/digest":
        return format_daily_digest(build_daily_report(db))
    return "Unknown command. Try /today /week /high /status"
