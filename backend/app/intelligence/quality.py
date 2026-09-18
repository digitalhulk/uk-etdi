"""Event quality, freshness and status engine (Phase 2).

Everything here is deterministic and config-driven (config/scoring.yaml → source_confidence_points, quality_points,
quality_levels, freshness, status_engine). Every score is returned with human-readable reasons.

Vocabulary
  source_confidence   OFFICIAL / TRUSTED / SECONDARY / UNVERIFIED / CURATED  (trust hierarchy; set per collector)
  event_quality_score 0..100  → quality_level HIGH / MEDIUM / LOW  (LOW → no automatic marketing)
  freshness_score     100 when verified now, linear decay to `floor` after `decay_days`
  status              SCHEDULED / CONFIRMED / POSTPONED / CANCELLED / RESCHEDULED / SOLD_OUT / COMPLETED / UNKNOWN
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from app.core.config import scoring_config

CONFIDENCE_ORDER = {"OFFICIAL": 4, "CURATED": 3, "TRUSTED": 3, "SECONDARY": 2, "UNVERIFIED": 1}


def _cfg(key: str, default: dict | None = None) -> dict:
    return scoring_config().get(key, default or {}) or (default or {})


@dataclass
class QualityResult:
    score: int
    level: str
    reasons: list[str] = field(default_factory=list)
    components: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "level": self.level, "reasons": self.reasons, "components": self.components}


def freshness_score(last_verified_at: datetime | None, now: datetime | None = None) -> int:
    f = _cfg("freshness", {"decay_days": 14, "floor": 10})
    if last_verified_at is None:
        return int(f.get("floor", 10))
    now = now or datetime.utcnow()
    age_days = max(0.0, (now - last_verified_at).total_seconds() / 86400)
    decay = float(f.get("decay_days", 14))
    floor = int(f.get("floor", 10))
    if age_days >= decay:
        return floor
    return int(round(100 - (100 - floor) * (age_days / decay)))


def is_source_silent(last_verified_at: datetime | None, date_start: date, now: datetime | None = None) -> bool:
    """Absence from a source is NOT cancellation — we only flag it. Past events are never 'silent'."""
    if last_verified_at is None or date_start < (now or datetime.utcnow()).date():
        return False
    days = int(_cfg("freshness").get("silent_after_days", 21))
    return ((now or datetime.utcnow()) - last_verified_at) > timedelta(days=days)


def best_confidence(confidences: list[str | None]) -> str:
    vals = [c for c in confidences if c]
    if not vals:
        return "UNVERIFIED"
    return max(vals, key=lambda c: CONFIDENCE_ORDER.get(c, 0))


def quality_for(*, source_confidence: str | None, time_start: str | None, venue_matched: bool, venue_named: bool, has_city: bool,
                official_url: str | None, has_geo: bool, category: str | None, source_count: int, freshness: int,
                is_school: bool = False, school_confidence: str | None = None) -> QualityResult:
    pts = _cfg("source_confidence_points")
    qp = _cfg("quality_points")
    levels = _cfg("quality_levels", {"HIGH": 70, "MEDIUM": 45, "LOW": 0})
    conf = source_confidence or "UNVERIFIED"
    comps: dict[str, int] = {}
    reasons: list[str] = []

    comps["source_confidence"] = int(pts.get(conf, pts.get("UNVERIFIED", 8)))
    reasons.append(f"Source confidence {conf} (+{comps['source_confidence']})")

    def add(key: str, ok: bool, label: str) -> None:
        if ok:
            comps[key] = int(qp.get(key, 0))
            reasons.append(f"{label} (+{comps[key]})")

    add("has_time", bool(time_start), "Start time known")
    if venue_matched:
        add("has_venue_matched", True, "Venue matched to registry")
    elif venue_named:
        add("has_venue_named", True, "Venue named (not in registry)")
    else:
        reasons.append("Venue unknown")
    add("has_city", has_city, "City resolved")
    add("has_official_url", bool(official_url), "Official URL present")
    add("has_postcode_or_coords", has_geo, "Postcode/coordinates known")
    add("category_classified", bool(category and category != "other"), f"Category classified as {category}")
    add("multi_source_bonus", source_count >= 2, f"Corroborated by {source_count} sources")
    if is_school and (school_confidence or "LOW").upper() != "HIGH":
        comps["school_event_penalty"] = int(qp.get("school_event_penalty", -20))
        reasons.append(f"School calendar event with {school_confidence or 'LOW'} confidence ({comps['school_event_penalty']})")
    if freshness < 40:
        comps["stale_penalty"] = int(qp.get("stale_penalty", -15))
        reasons.append(f"Stale: freshness {freshness} ({comps['stale_penalty']})")

    score = max(0, min(100, sum(comps.values())))
    level = "LOW"
    for lvl in ("HIGH", "MEDIUM", "LOW"):
        if score >= int(levels.get(lvl, 0)):
            level = lvl
            break
    return QualityResult(score=score, level=level, reasons=reasons, components=comps)


def _kw_hit(text: str, kws: list[str]) -> str | None:
    t = f" {text.lower()} "
    for k in kws:
        if k in t:
            return k
    return None


def derive_status(*, current_status: str, incoming_status: str | None, incoming_confidence: str | None, title: str, sold_out: bool,
                  source_count: int, date_start: date, date_changed: bool, today: date | None = None) -> tuple[str, str]:
    """Status engine. Returns (status, reason). Rules (first match wins):
    1. explicit CANCELLED/POSTPONED from any source, or cancellation keywords in title → that status
    2. date changed on an existing event → RESCHEDULED
    3. sold-out signal → SOLD_OUT
    4. event date in the past → COMPLETED
    5. corroborated by ≥ N sources or explicit CONFIRMED from an OFFICIAL source → CONFIRMED
    6. otherwise keep SCHEDULED (never downgrade CONFIRMED to SCHEDULED just because a source went quiet)."""
    se = _cfg("status_engine")
    today = today or date.today()
    inc = (incoming_status or "").upper()
    kw = _kw_hit(title, se.get("cancelled_keywords", []))
    if inc == "CANCELLED" or kw:
        return "CANCELLED", f"Source reported cancelled" if inc == "CANCELLED" else f"Title contains '{kw}'"
    kw = _kw_hit(title, se.get("postponed_keywords", []))
    if inc == "POSTPONED" or kw:
        return "POSTPONED", "Source reported postponed" if inc == "POSTPONED" else f"Title contains '{kw}'"
    if inc == "RESCHEDULED" or date_changed or _kw_hit(title, se.get("rescheduled_keywords", [])):
        return "RESCHEDULED", "Event date changed since first seen" if date_changed else "Source reported rescheduled"
    if current_status in ("CANCELLED", "POSTPONED") and inc in ("", "SCHEDULED", "UNKNOWN"):
        return current_status, f"Previously {current_status.lower()}; a plain listing does not reverse it"
    if sold_out or inc == "SOLD_OUT":
        return "SOLD_OUT", "Ticket availability reported as sold out"
    if date_start < today:
        return "COMPLETED", "Event date has passed"
    n = int(se.get("confirm_when_sources_gte", 2))
    if inc == "CONFIRMED" and (incoming_confidence or "") == "OFFICIAL":
        return "CONFIRMED", "Confirmed by official source"
    if source_count >= n:
        return "CONFIRMED", f"Corroborated by {source_count} independent sources"
    if current_status == "CONFIRMED":
        return "CONFIRMED", "Previously confirmed"
    if inc in ("SCHEDULED", "", "UNKNOWN"):
        return "SCHEDULED", "Listed by source; single-source, not yet corroborated"
    return inc, "Source-reported status"
