"""Taxi opportunity engine: turns a scored event into typed journey opportunities with modelled windows.

v2 scoring is additive and transparent (config/scoring.yaml → opportunity_v2):
    score = demand_component + quality_component + freshness_component + service_area_component
where demand_component = opportunity_score × type_factor × weight. Each opportunity stores `score_components`."""
from __future__ import annotations

from app.core.config import get_settings, scoring_config
from app.db.models import Event
from app.processors.normalize import normalize_name

from .demand_score import demand_level_for


def in_service_area(event: Event, service_area: set[str] | None = None) -> bool:
    from app.core.service_area import current
    sa = service_area if service_area is not None else current()["normalized"]
    city = event.city.normalized_name if event.city else normalize_name(event.city_name_raw)
    return bool(city) and city in sa


def opportunity_v2(event: Event, opp_type: str, service_area: set[str] | None = None) -> tuple[int, dict]:
    cfg = scoring_config().get("opportunity_v2", {}) or {}
    w = cfg.get("components", {"demand": 55, "quality": 20, "freshness": 10, "service_area": 15})
    tf = float((cfg.get("type_factors") or {}).get(opp_type, 0.8))
    demand = int(event.opportunity_score or 0)
    quality = int(event.event_quality_score or 0)
    fresh = int(event.freshness_score if event.freshness_score is not None else 50)
    sa = in_service_area(event, service_area)
    comps = {
        "demand": round(demand * tf * w.get("demand", 55) / 100, 1),
        "quality": round(quality * w.get("quality", 20) / 100, 1),
        "freshness": round(fresh * w.get("freshness", 10) / 100, 1),
        "service_area": float(w.get("service_area", 15)) if sa else 0.0,
    }
    total = max(0, min(100, int(round(sum(comps.values())))))
    return total, {"components": comps, "weights": w, "inputs": {"opportunity_score": demand, "type_factor": tf, "event_quality_score": quality,
                                                                    "freshness_score": fresh, "in_service_area": sa}, "formula": "sum(components)", "version": 2}

TYPES = ["HOME_TO_VENUE", "STATION_TO_VENUE", "HOTEL_TO_VENUE", "AIRPORT_TO_VENUE", "VENUE_TO_HOME", "VENUE_TO_HOTEL",
         "VENUE_TO_STATION", "VENUE_TO_AIRPORT", "LATE_NIGHT_RETURN", "PRE_BOOKING"]


def generate_opportunities(event: Event) -> list[dict]:
    min_score = scoring_config().get("opportunity_thresholds", {}).get("generate_taxi_opportunities_min_score", 35)
    if event.opportunity_score < min_score or event.status in ("CANCELLED", "POSTPONED", "COMPLETED"):
        return []
    base = event.opportunity_score
    venue = event.venue
    city = event.city
    w = event.demand_windows or {}
    pre = w.get("pre_event_window") or {}
    post = w.get("post_event_window") or {}
    tourism = float(city.tourism) if city else 0.2
    station_km = venue.station_distance_km if venue else None
    airport_km = venue.airport_distance_km if venue else None
    late = bool(event.time_start and int(event.time_start[:2]) >= 18)
    name = venue.name if venue else (event.city_name_raw or "venue")

    from app.core.service_area import current
    service_area = current()["normalized"]

    def mk(t: str, factor: float, reasons: list[str], window: dict, action: str) -> dict:
        s, comps = opportunity_v2(event, t, service_area)
        comps["legacy_factor"] = factor
        reasons = list(reasons) + [f"Event quality {event.quality_level or 'n/a'} ({event.event_quality_score or 0})",
                                   "Inside service area" if comps["inputs"]["in_service_area"] else "Outside configured service area"]
        return {"opportunity_type": t, "score": s, "demand_level": demand_level_for(s), "window_start": window.get("start"),
                "window_end": window.get("end"), "window_label": "Modelled demand window", "reasons": reasons, "recommended_action": action,
                "score_components": comps, "confidence": event.quality_level or "LOW"}

    out = [
        mk("HOME_TO_VENUE", 0.9, ["Local arrivals before start", "Pre-event pickup demand"], pre, f"Position drivers in residential zones 2–3h before start; promote pre-booking to {name}."),
        mk("VENUE_TO_HOME", 1.0, ["Peak departure surge at end", "Largest single demand spike"], post, f"Stage vehicles near {name} exits from the end time; enable surge-ready dispatch."),
    ]
    if station_km is not None:
        sf = 0.85 if station_km > 1.5 else 0.6
        out.append(mk("STATION_TO_VENUE", sf, [f"Nearest station ≈ {station_km} km", "Rail arrivals need last-mile transfer"], pre, "Advertise station-to-venue transfers; rank at station taxi rank."))
        out.append(mk("VENUE_TO_STATION", sf, ["Rail return journeys after event", "Last train pressure"], post, "Offer fixed-price venue→station fares."))
    if tourism >= 0.5:
        out.append(mk("HOTEL_TO_VENUE", 0.5 + tourism * 0.3, [f"Tourism factor {tourism:.1f}", "Visitors staying in hotels"], pre, "Partner with hotel concierges; place QR booking cards."))
        out.append(mk("VENUE_TO_HOTEL", 0.5 + tourism * 0.3, ["Hotel returns after event"], post, "Target hotel-district returns in dispatch."))
    if airport_km is not None and airport_km <= 20:
        af = 0.8 if airport_km <= 8 else 0.6
        out.append(mk("AIRPORT_TO_VENUE", af, [f"Airport ≈ {airport_km:.0f} km"], pre, "Bid on airport-transfer keywords for event dates."))
        out.append(mk("VENUE_TO_AIRPORT", af * 0.9, ["Post-event airport transfers"], post, "Offer pre-bookable airport transfers."))
    if late:
        out.append(mk("LATE_NIGHT_RETURN", 0.95, ["Evening start — late finish", "Reduced public transport late night"], post, "Extend night shift coverage; push 'safe ride home' messaging."))
    out.append(mk("PRE_BOOKING", 0.8, ["Advance bookings reduce dispatch pressure"], {"start": "00:00", "end": "23:59"}, "Run pre-booking campaign 3–7 days ahead."))
    return out
