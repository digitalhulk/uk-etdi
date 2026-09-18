"""Event ↔ booking correlation (section 32). Purely spatial-temporal matching; never asserts causation."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import load_config
from app.db.models import Event, EventBookingCorrelation, TaxiBooking


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def _params() -> dict:
    cfg = (load_config("bookings.yaml") or {}).get("correlation") or {}
    return {"radius_km": float(cfg.get("radius_km", 1.0)), "pre_minutes": int(cfg.get("pre_minutes", 180)),
            "post_minutes": int(cfg.get("post_minutes", 240)), "default_duration_min": int(cfg.get("default_duration_min", 150))}


def match_confidence(distance_km: float, time_delta_min: int, radius_km: float, window_min: int) -> float:
    """Linear decay on both axes, product combined. 1.0 = at the venue exactly at the boundary time."""
    d = max(0.0, 1.0 - distance_km / radius_km)
    t = max(0.0, 1.0 - abs(time_delta_min) / max(window_min, 1))
    return round(d * (0.5 + 0.5 * t), 3)


def correlate(db: Session, since: date | None = None, until: date | None = None) -> dict[str, int]:
    p = _params()
    stats = {"events": 0, "bookings_considered": 0, "correlations": 0}
    q = select(Event).where(Event.latitude.isnot(None), Event.longitude.isnot(None), Event.time_start.isnot(None))
    if since:
        q = q.where(Event.date_start >= since)
    if until:
        q = q.where(Event.date_start <= until)
    events = db.scalars(q).all()
    if not events:
        return stats
    for ev in events:
        stats["events"] += 1
        hh, mm = map(int, ev.time_start.split(":")[:2])
        start = datetime.combine(ev.date_start, datetime.min.time()).replace(hour=hh, minute=mm)
        end = start + timedelta(minutes=p["default_duration_min"])
        lo, hi = start - timedelta(minutes=p["pre_minutes"]), end + timedelta(minutes=p["post_minutes"])
        db.execute(delete(EventBookingCorrelation).where(EventBookingCorrelation.event_id == ev.id))
        # coarse bbox (~radius) before exact haversine
        dlat = p["radius_km"] / 111.0
        dlon = p["radius_km"] / (111.0 * max(cos(radians(ev.latitude)), 0.2))
        bq = select(TaxiBooking).where(TaxiBooking.pickup_datetime >= lo, TaxiBooking.pickup_datetime <= hi)
        for b in db.scalars(bq):
            stats["bookings_considered"] += 1
            for leg, lat, lon in (("DROPOFF", b.dropoff_lat, b.dropoff_lon), ("PICKUP", b.pickup_lat, b.pickup_lon)):
                if lat is None or lon is None or abs(lat - ev.latitude) > dlat or abs(lon - ev.longitude) > dlon:
                    continue
                dist = haversine_km(lat, lon, ev.latitude, ev.longitude)
                if dist > p["radius_km"]:
                    continue
                delta = int((b.pickup_datetime - start).total_seconds() // 60)
                # dropoffs at the venue make sense before start; pickups from the venue after the end
                window = p["pre_minutes"] if leg == "DROPOFF" else p["post_minutes"] + p["default_duration_min"]
                if (leg == "DROPOFF" and delta > 30) or (leg == "PICKUP" and delta < 0):
                    continue
                conf = match_confidence(dist, delta if leg == "DROPOFF" else delta - p["default_duration_min"], p["radius_km"], window)
                db.add(EventBookingCorrelation(event_id=ev.id, booking_id=b.id, leg=leg, distance_km=round(dist, 3), time_delta_min=delta,
                                               match_confidence=conf))
                stats["correlations"] += 1
    db.commit()
    return stats
