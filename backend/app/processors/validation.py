"""Validates normalized events before persistence. Returns (valid, reasons)."""
from __future__ import annotations

from datetime import date, timedelta

from app.schemas.normalized import NormalizedEvent

MAX_FUTURE_DAYS = 400
MAX_PAST_DAYS = 2


def _non_event_patterns() -> tuple[str, ...]:
    from app.core.config import load_config
    return tuple(str(x).lower() for x in load_config("categories.yaml").get("non_event_title_patterns", []) or [])


def validate(ev: NormalizedEvent, today: date | None = None) -> tuple[bool, list[str]]:
    today = today or date.today()
    problems: list[str] = []
    if not ev.title or len(ev.title.strip()) < 3:
        problems.append("title_too_short")
    if not ev.external_id:
        problems.append("missing_external_id")
    if ev.date_start < today - timedelta(days=MAX_PAST_DAYS):
        problems.append("event_in_past")
    if ev.date_start > today + timedelta(days=MAX_FUTURE_DAYS):
        problems.append("event_too_far_future")
    if ev.date_end and ev.date_end < ev.date_start:
        problems.append("end_before_start")
    if not (ev.venue_name or ev.city_name or (ev.latitude and ev.longitude)):
        problems.append("no_location")
    tl = (ev.title or "").lower()
    if any(pat in tl for pat in _non_event_patterns()):
        problems.append("non_event_title")
    return (not problems, problems)
