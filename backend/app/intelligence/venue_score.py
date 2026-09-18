"""Venue intelligence: capacity band factor + importance, and transport access factor."""
from __future__ import annotations

from app.core.config import scoring_config
from app.db.models import Venue


def capacity_factor(capacity: int | None) -> float:
    if not capacity:
        return 0.0
    for band in scoring_config().get("capacity_bands", []):
        if capacity >= band["min"]:
            return float(band["factor"])
    return 0.1


def venue_scale(venue: Venue | None) -> tuple[float, str]:
    if venue is None:
        return 0.15, "Venue unknown"
    if not venue.capacity:
        return 0.3, f"{venue.name}: capacity not published"
    f = capacity_factor(venue.capacity)
    f = min(1.0, 0.8 * f + 0.2 * (venue.importance_score or 0))
    label = "Major venue" if f >= 0.8 else "Large venue" if f >= 0.6 else "Mid-size venue" if f >= 0.4 else "Small venue"
    return f, f"{label} ({venue.name}, capacity {venue.capacity:,})"


def transport_factor(venue: Venue | None) -> tuple[float, str]:
    """Taxi demand is highest when a venue is large AND rail access is imperfect; strong station links reduce share
    but airport proximity adds airport transfer opportunities. Returns 0..1."""
    if venue is None or venue.station_distance_km is None:
        return 0.5, "Transport access unknown"
    s = venue.station_distance_km
    a = venue.airport_distance_km or 50
    station_component = 0.35 if s <= 0.5 else 0.55 if s <= 1.5 else 0.8 if s <= 3 else 1.0
    airport_component = 0.3 if a <= 5 else 0.15 if a <= 15 else 0.0
    f = min(1.0, station_component + airport_component)
    desc = ("Strong rail connectivity" if s <= 0.5 else "Moderate rail access" if s <= 1.5 else "Limited rail access — taxi reliant")
    if a <= 15:
        desc += f"; airport {a:.0f} km"
    return f, desc
