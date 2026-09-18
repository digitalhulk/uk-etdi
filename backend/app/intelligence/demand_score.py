"""Transparent demand scoring (0–100). Weights from config/scoring.yaml. Every score returns reasons."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.core.config import get_settings, scoring_config
from app.db.models import City, Venue
from app.processors.classify import category_factor
from app.processors.normalize import normalize_name

from .venue_score import capacity_factor, transport_factor, venue_scale


@dataclass
class ScoreResult:
    score: int
    demand_level: str
    marketing_priority: str | None
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    attendance_estimate: int | None = None
    attendance_confidence: str | None = None
    windows: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"score": self.score, "demand_level": self.demand_level, "components": self.components, "reasons": self.reasons,
                "weights": scoring_config().get("weights", {}), "note": "Modelled score; not observed taxi demand."}


def demand_level_for(score: int) -> str:
    levels = scoring_config().get("demand_levels", {})
    for name, threshold in sorted(levels.items(), key=lambda kv: -kv[1]):
        if score >= threshold:
            return name
    return "LOW"


def marketing_priority_for(score: int) -> str | None:
    for name, threshold in sorted(scoring_config().get("marketing_priority", {}).items(), key=lambda kv: -kv[1]):
        if score >= threshold:
            return name
    return None


def estimate_attendance(category: str, venue: Venue | None) -> tuple[int | None, str | None]:
    if not venue or not venue.capacity:
        return None, None
    rate = float(scoring_config().get("fill_rates", {}).get(category, 0.5))
    return int(venue.capacity * rate), "MEDIUM" if venue.is_seeded else "LOW"


def _timing(date_start: date, time_start: str | None, time_end: str | None) -> tuple[float, list[str]]:
    cfg = scoring_config().get("timing", {})
    reasons = []
    if time_start:
        h = int(time_start[:2])
        if h >= cfg.get("evening_start_hour", 17):
            f = 0.75
            reasons.append("Evening event — late return journeys")
        elif h >= 12:
            f = 0.5
            reasons.append("Afternoon event")
        else:
            f = 0.35
            reasons.append("Morning start")
        if time_end and int(time_end[:2]) >= cfg.get("late_finish_hour", 22):
            f += 0.15
            reasons.append("Late finish after public transport thins out")
    else:
        f = float(cfg.get("unknown_time_factor", 0.5))
        reasons.append("Start time not yet confirmed")
    wd = date_start.weekday()
    if wd >= 5:
        f += float(cfg.get("weekend_bonus", 0.25))
        reasons.append("Weekend")
    elif wd == 4:
        f += float(cfg.get("friday_bonus", 0.15))
        reasons.append("Friday")
    return min(f, 1.0), reasons


def _location(city: City | None) -> tuple[float, list[str]]:
    if city is None:
        return 0.2, ["City unresolved"]
    from app.core.service_area import current
    service_area = current()["normalized"]
    f = (city.priority or 50) / 100
    reasons = [f"{city.name} (priority {city.priority})"]
    if city.normalized_name in service_area:
        f = min(1.0, f + 0.2)
        reasons.append("Inside taxi service area")
    return f, reasons


def _duration(category: str, date_start: date, date_end: date | None, time_start: str | None, time_end: str | None) -> tuple[float, str]:
    if date_end and date_end > date_start:
        days = (date_end - date_start).days + 1
        return min(1.0, 0.5 + days * 0.1), f"Multi-day event ({days} days)"
    if time_start and time_end:
        hours = (int(time_end[:2]) - int(time_start[:2])) % 24
        return min(1.0, hours / 8), f"Duration ≈ {hours}h"
    default = scoring_config().get("windows", {}).get("default_duration_hours", {}).get(category, 3)
    return min(1.0, default / 8), f"Typical {category} duration ≈ {default}h (modelled)"


def compute_windows(category: str, date_start: date, time_start: str | None, time_end: str | None) -> dict:
    cfg = scoring_config().get("windows", {})
    if not time_start:
        return {"label": "Modelled demand window", "available": False, "reason": "Start time unknown"}
    start = datetime.combine(date_start, datetime.strptime(time_start, "%H:%M").time())
    if time_end:
        end = datetime.combine(date_start, datetime.strptime(time_end, "%H:%M").time())
        if end <= start:
            end += timedelta(days=1)
    else:
        end = start + timedelta(hours=float(cfg.get("default_duration_hours", {}).get(category, 3)))
    pre = start - timedelta(hours=float(cfg.get("pre_event_hours", 3)))
    post = end + timedelta(hours=float(cfg.get("post_event_hours", 2.5)))
    fmt = lambda d: d.strftime("%H:%M")  # noqa: E731
    return {
        "label": "Modelled demand window", "available": True,
        "pre_event_window": {"start": fmt(pre), "end": fmt(start), "type": "arrivals"},
        "event_window": {"start": fmt(start), "end": fmt(end), "type": "in_progress"},
        "post_event_window": {"start": fmt(end), "end": fmt(post), "type": "departures", "peak": fmt(end + timedelta(minutes=20))},
        "end_estimated": not bool(time_end),
    }


def score_event(*, category: str, date_start: date, date_end: date | None, time_start: str | None, time_end: str | None,
                venue: Venue | None, city: City | None, recurrence: str | None = None, status: str = "SCHEDULED") -> ScoreResult:
    w = scoring_config().get("weights", {})
    comps: dict[str, float] = {}
    reasons: list[str] = []

    attendance, conf = estimate_attendance(category, venue)
    ef = capacity_factor(attendance) if attendance else 0.15
    comps["event_scale"] = round(ef * w.get("event_scale", 20), 1)
    reasons.append(f"Modelled attendance ≈ {attendance:,}" if attendance else "Attendance unknown (no published capacity)")

    vf, vr = venue_scale(venue)
    comps["venue_scale"] = round(vf * w.get("venue_scale", 20), 1)
    reasons.append(vr)

    tf, tr = _timing(date_start, time_start, time_end)
    comps["timing"] = round(tf * w.get("timing", 15), 1)
    reasons.extend(tr)

    lf, lr = _location(city)
    comps["location"] = round(lf * w.get("location", 15), 1)
    reasons.extend(lr)

    trf, trr = transport_factor(venue)
    comps["transport"] = round(trf * w.get("transport", 10), 1)
    reasons.append(trr)

    cf = category_factor(category)
    comps["category"] = round(cf * w.get("category", 10), 1)
    reasons.append(f"Category: {category}")

    tour = float(city.tourism) if city else 0.2
    comps["tourism"] = round(tour * w.get("tourism", 5), 1)
    if tour >= 0.7:
        reasons.append("High-tourism city — hotel/airport transfers")

    df, dr = _duration(category, date_start, date_end, time_start, time_end)
    comps["duration"] = round(df * w.get("duration", 5), 1)
    reasons.append(dr)

    total = int(round(sum(comps.values())))
    if status in ("CANCELLED", "POSTPONED"):
        total = 0
        reasons.insert(0, f"Event {status.lower()} — no demand expected")
    total = max(0, min(100, total))
    return ScoreResult(score=total, demand_level=demand_level_for(total), marketing_priority=marketing_priority_for(total),
                       components=comps, reasons=reasons, attendance_estimate=attendance, attendance_confidence=conf,
                       windows=compute_windows(category, date_start, time_start, time_end))
