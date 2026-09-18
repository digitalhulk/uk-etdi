"""Compares an existing Event row against a fresh NormalizedEvent and emits change records."""
from __future__ import annotations

from app.db.models import Event
from rapidfuzz import fuzz

from app.processors.normalize import normalize_title
from app.schemas.normalized import NormalizedEvent

TRACKED = [
    ("date_start", "DATE_CHANGED"),
    ("date_end", "DATE_CHANGED"),
    ("time_start", "TIME_CHANGED"),
    ("time_end", "TIME_CHANGED"),
    ("venue_name_raw", "VENUE_CHANGED"),
    ("title", "UPDATED"),
    ("ticket_url", "UPDATED"),
    ("official_url", "UPDATED"),
]


def _depth(u: str) -> int:
    from urllib.parse import urlparse
    return len([p for p in urlparse(u).path.split("/") if p])


def detect_changes(existing: Event, incoming: NormalizedEvent, *, title: str | None = None, include_status: bool = True) -> list[dict]:
    """`title` lets the caller pass the cleaned title actually stored; `include_status=False` defers status to the status engine."""
    changes: list[dict] = []
    mapping = {
        "date_start": incoming.date_start,
        "date_end": incoming.date_end,
        "time_start": incoming.time_start,
        "time_end": incoming.time_end,
        "venue_name_raw": incoming.venue_name,
        "title": title if title is not None else incoming.title,
        "ticket_url": incoming.ticket_url,
        "official_url": incoming.official_url,
    }
    for field, ctype in TRACKED:
        new = mapping[field]
        old = getattr(existing, field)
        if new is None:
            continue  # do not treat missing data as a change
        if field == "title" and old and fuzz.token_set_ratio(normalize_title(str(old)), normalize_title(str(new))) >= 80:
            continue  # wording variants of the same title are not a material change
        if field in ("official_url", "ticket_url") and old and _depth(str(new)) <= _depth(str(old)) and str(new) != str(old):
            continue  # a generic/listing URL replacing a specific one is not a material change (and is not applied)
        if str(old).strip() != str(new).strip():
            changes.append({"change_type": ctype, "field": field, "old_value": str(old), "new_value": str(new)})

    if include_status and incoming.status != existing.status:
        if incoming.status == "CANCELLED":
            ctype = "CANCELLED"
        elif incoming.status == "POSTPONED":
            ctype = "POSTPONED"
        else:
            ctype = "STATUS_CHANGED"
        changes.append({"change_type": ctype, "field": "status", "old_value": existing.status, "new_value": incoming.status})
    return changes
