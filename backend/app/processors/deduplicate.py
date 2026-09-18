"""Exact fingerprint + fuzzy matching. Low-confidence matches are NOT merged automatically."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz

from .normalize import normalize_name, normalize_title

AUTO_MERGE_THRESHOLD = 0.88
REVIEW_THRESHOLD = 0.70


def fingerprint(title: str, date_start: date, venue: str | None, city: str | None) -> str:
    key = "|".join([normalize_title(title), date_start.isoformat(), normalize_name(venue), normalize_name(city)])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass
class DuplicateCandidate:
    event_id: int
    confidence: float
    reason: str

    @property
    def auto_merge(self) -> bool:
        return self.confidence >= AUTO_MERGE_THRESHOLD


def similarity(title_a: str, title_b: str, venue_a: str | None, venue_b: str | None,
               city_a: str | None, city_b: str | None, same_date: bool) -> tuple[float, str]:
    """Fuzzy duplicate confidence in 0..1 with a human-readable reason."""
    if not same_date:
        return 0.0, "different_date"
    t = fuzz.token_set_ratio(normalize_title(title_a), normalize_title(title_b)) / 100
    v = 1.0 if normalize_name(venue_a) and normalize_name(venue_a) == normalize_name(venue_b) else (
        fuzz.token_set_ratio(normalize_name(venue_a), normalize_name(venue_b)) / 100 if venue_a and venue_b else 0.5)
    c = 1.0 if normalize_name(city_a) == normalize_name(city_b) else 0.3
    score = 0.6 * t + 0.25 * v + 0.15 * c
    reason = f"title={t:.2f} venue={v:.2f} city={c:.2f}"
    return round(score, 3), reason
