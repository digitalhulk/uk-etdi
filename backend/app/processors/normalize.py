"""Normalization helpers: names, titles, UK dates/times, URLs, statuses. Timezone: Europe/London (GMT/BST aware)."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dateutil import parser as dtparser

LONDON = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")

_STOPWORDS = {"the", "a", "an", "at", "of", "and", "&", "live", "in", "presents", "official"}
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")
_UK_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(s: str | None) -> str:
    if not s:
        return ""
    s = strip_accents(s).lower().replace("&", " and ").replace("'", "")
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def normalize_title(title: str) -> str:
    base = normalize_name(title)
    tokens = [t for t in base.split(" ") if t and t not in _STOPWORDS]
    return " ".join(tokens)


def clean_title(title: str) -> str:
    return _WS.sub(" ", (title or "").strip())[:300]


def normalize_postcode(pc: str | None) -> str | None:
    if not pc:
        return None
    pc = re.sub(r"\s+", "", pc.upper())
    if len(pc) < 5 or len(pc) > 7:
        return None
    return f"{pc[:-3]} {pc[-3:]}"


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url[:600] or None


def parse_uk_date(value: str | date | datetime | None) -> date | None:
    """Accepts DD/MM/YYYY, YYYY-MM-DD, ISO datetimes and natural-language ('Sat 21 Sep 2026')."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    m = _UK_DATE.match(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    try:
        return dtparser.parse(s, dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def parse_time(value: str | None) -> str | None:
    """Returns HH:MM or None when the time is unknown/TBC."""
    if not value:
        return None
    s = str(value).strip().lower()
    if s in {"tbc", "tba", "tbd", "unknown", ""}:
        return None
    m = re.match(r"^(\d{1,2})[.:](\d{2})\s*(am|pm)?$", s)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None
    try:
        t = dtparser.parse(s, fuzzy=True).time()
        return t.strftime("%H:%M")
    except (ValueError, OverflowError):
        return None


def utc_to_london(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)
    return dt_utc.astimezone(LONDON)


def split_local(dt_utc: datetime) -> tuple[date, str]:
    local = utc_to_london(dt_utc)
    return local.date(), local.strftime("%H:%M")


def local_datetime(d: date, hhmm: str | None) -> datetime | None:
    if not hhmm:
        return None
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=LONDON)


STATUS_MAP = {
    "onsale": "SCHEDULED", "scheduled": "SCHEDULED", "eventscheduled": "SCHEDULED", "live": "SCHEDULED",
    "offsale": "SCHEDULED", "cancelled": "CANCELLED", "canceled": "CANCELLED", "eventcancelled": "CANCELLED",
    "postponed": "POSTPONED", "eventpostponed": "POSTPONED", "rescheduled": "RESCHEDULED",
    "eventrescheduled": "RESCHEDULED", "movedonline": "SCHEDULED", "completed": "COMPLETED",
}


def normalize_status(value: str | None) -> str:
    if not value:
        return "SCHEDULED"
    key = re.sub(r"[^a-z]", "", str(value).lower().split("/")[-1])
    return STATUS_MAP.get(key, "SCHEDULED")
