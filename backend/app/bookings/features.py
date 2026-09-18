"""Demand-forecast feature pipeline (section 33).

Mode is DETERMINISTIC until enough labelled events exist (config/bookings.yaml → forecast.min_labelled_events);
we never claim ML accuracy without training data. When the threshold is met the mode flips to FORECAST and a simple,
inspectable model (per-category median bookings scaled by capacity ratio) is used — still fully explainable."""
from __future__ import annotations

from datetime import date
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import load_config
from app.db.models import DemandFeatureRow, Event, EventBookingCorrelation
from app.providers import get_external_data_provider


def build_features(ev: Event) -> dict:
    weather = get_external_data_provider("weather")
    traffic = get_external_data_provider("traffic")
    transport = get_external_data_provider("transport")
    hh = int(ev.time_start.split(":")[0]) if ev.time_start else None
    return {
        "event_type": ev.category, "event_subtype": ev.subcategory, "event_score": ev.opportunity_score, "quality_score": ev.event_quality_score,
        "venue_id": ev.venue_id, "capacity": ev.venue_capacity, "city_id": ev.city_id, "day_of_week": ev.date_start.weekday(),
        "start_hour": hh, "is_weekend": ev.date_start.weekday() >= 5, "status": ev.status, "source_confidence": ev.source_confidence,
        # external features: null until a provider is configured (never invented)
        "weather": weather.fetch(lat=ev.latitude, lon=ev.longitude, date=ev.date_start.isoformat()) if weather.is_configured() else None,
        "traffic": traffic.fetch(lat=ev.latitude, lon=ev.longitude) if traffic.is_configured() else None,
        "transport_disruptions": transport.fetch(city_id=ev.city_id, date=ev.date_start.isoformat()) if transport.is_configured() else None,
    }


def labelled_count(db: Session) -> int:
    return db.scalar(select(func.count(func.distinct(EventBookingCorrelation.event_id)))) or 0


def forecast_mode(db: Session) -> tuple[str, dict]:
    cfg = (load_config("bookings.yaml") or {}).get("forecast") or {}
    need = int(cfg.get("min_labelled_events", 200))
    have = labelled_count(db)
    return ("FORECAST" if have >= need else "DETERMINISTIC"), {"labelled_events": have, "required": need}


def refresh_features(db: Session, since: date | None = None) -> dict:
    mode, info = forecast_mode(db)
    labels = dict(db.execute(select(EventBookingCorrelation.event_id, func.count(EventBookingCorrelation.id)).group_by(EventBookingCorrelation.event_id)).all())
    q = select(Event)
    if since:
        q = q.where(Event.date_start >= since)
    existing = {r.event_id: r for r in db.scalars(select(DemandFeatureRow)).all()}
    n = 0
    for ev in db.scalars(q):
        feats = build_features(ev)
        row = existing.get(ev.id)
        if row is None:
            row = DemandFeatureRow(event_id=ev.id, features=feats)
            db.add(row)
        else:
            row.features = feats
        row.label_bookings = labels.get(ev.id)
        row.model_mode = mode
        n += 1
    db.commit()
    return {"mode": mode, **info, "rows": n}


def forecast_bookings(db: Session, ev: Event) -> dict:
    """Explainable estimate. DETERMINISTIC → None (we do not guess). FORECAST → per-category median of observed labels,
    scaled by capacity ratio, with the sample size reported."""
    mode, info = forecast_mode(db)
    if mode != "FORECAST":
        return {"mode": mode, "estimate": None, "reason": f"Only {info['labelled_events']}/{info['required']} labelled events; deterministic scoring in use."}
    rows = db.execute(select(DemandFeatureRow.features, DemandFeatureRow.label_bookings)
                      .where(DemandFeatureRow.label_bookings.isnot(None))).all()
    same = [(f, y) for f, y in rows if f.get("event_type") == ev.category and y is not None]
    if len(same) < 10:
        return {"mode": mode, "estimate": None, "reason": f"Only {len(same)} labelled {ev.category} events (need 10)."}
    med = median(y for _, y in same)
    caps = [f.get("capacity") for f, _ in same if f.get("capacity")]
    ratio = (ev.venue_capacity / median(caps)) if caps and ev.venue_capacity else 1.0
    est = round(med * min(max(ratio, 0.2), 5.0))
    return {"mode": mode, "estimate": est, "sample": len(same), "method": "category_median × capacity_ratio", "label": "FORECAST (observed history)"}
