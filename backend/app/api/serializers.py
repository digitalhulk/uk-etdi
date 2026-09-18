from __future__ import annotations

from app.db.models import Event, EventChange, MarketingAction, Opportunity, Source, Venue


def event_summary(e: Event) -> dict:
    return {
        "id": e.id, "canonical_event_id": e.canonical_event_id, "title": e.title, "category": e.category, "subcategory": e.subcategory,
        "date_start": e.date_start.isoformat(), "date_end": e.date_end.isoformat() if e.date_end else None,
        "time_start": e.time_start, "time_end": e.time_end, "timezone": e.timezone,
        "venue": {"id": e.venue.id, "name": e.venue.name, "capacity": e.venue.capacity} if e.venue else {"id": None, "name": e.venue_name_raw, "capacity": None},
        "city": e.city.name if e.city else e.city_name_raw, "region": e.region.name if e.region else None, "postcode": e.postcode,
        "latitude": e.latitude, "longitude": e.longitude, "status": e.status, "opportunity_score": e.opportunity_score,
        "demand_level": e.demand_level, "marketing_priority": e.marketing_priority, "primary_source": e.primary_source,
        "official_url": e.official_url, "ticket_url": e.ticket_url, "last_updated_at": e.last_updated_at.isoformat() if e.last_updated_at else None,
        "source_confidence": e.source_confidence, "event_quality_score": e.event_quality_score, "quality_level": e.quality_level,
        "freshness_score": e.freshness_score, "last_verified_at": e.last_verified_at.isoformat() if e.last_verified_at else None,
        "status_reason": e.status_reason, "source_count": e.source_count, "event_subtype": e.event_subtype,
    }


def event_detail(e: Event) -> dict:
    d = event_summary(e)
    d.update({
        "description": e.description, "organizer": e.organizer, "attendance_estimate": e.attendance_estimate,
        "attendance_confidence": e.attendance_confidence, "attendance_note": "Modelled estimate (capacity × typical fill rate)" if e.attendance_estimate else None,
        "venue_capacity": e.venue_capacity, "recurrence": e.recurrence, "first_seen_at": e.first_seen_at.isoformat(), "last_seen_at": e.last_seen_at.isoformat(),
        "score_breakdown": e.score_breakdown, "demand_windows": e.demand_windows,
        "opportunities": [opportunity(o) for o in sorted(e.opportunities, key=lambda o: -o.score)],
        "marketing_actions": [action(a) for a in e.marketing_actions],
        "changes": [change(c) for c in sorted(e.changes, key=lambda c: c.detected_at, reverse=True)],
        "sources": [{"source": s.source.key, "external_id": s.external_id, "url": s.source_url, "first_seen": s.first_seen.isoformat(), "last_seen": s.last_seen.isoformat()} for s in e.sources],
        "venue_detail": venue(e.venue) if e.venue else None,
        "quality_reasons": e.quality_reasons or [],
        # Explicit provenance split for the UI: what is sourced vs modelled vs recommended.
        "facts": {
            "title": e.title, "date_start": e.date_start.isoformat(), "date_end": e.date_end.isoformat() if e.date_end else None,
            "time_start": e.time_start, "time_end": e.time_end, "venue": e.venue.name if e.venue else e.venue_name_raw,
            "venue_capacity": e.venue.capacity if e.venue else None, "venue_capacity_source": e.venue.capacity_source if e.venue else None,
            "city": e.city.name if e.city else e.city_name_raw, "postcode": e.postcode, "status": e.status, "status_reason": e.status_reason,
            "official_url": e.official_url, "ticket_url": e.ticket_url, "organizer": e.organizer,
            "sources": [{"source": s.source.key, "url": s.source_url, "last_seen": s.last_seen.isoformat()} for s in e.sources],
            "source_confidence": e.source_confidence, "last_verified_at": e.last_verified_at.isoformat() if e.last_verified_at else None,
        },
        "modelled": {
            "opportunity_score": e.opportunity_score, "demand_level": e.demand_level, "score_breakdown": e.score_breakdown,
            "attendance_estimate": e.attendance_estimate, "attendance_confidence": e.attendance_confidence,
            "demand_windows": e.demand_windows, "event_quality_score": e.event_quality_score, "quality_level": e.quality_level,
            "quality_reasons": e.quality_reasons or [], "freshness_score": e.freshness_score, "label": "MODELLED",
        },
        "recommendations": {
            "opportunities": [opportunity(o) for o in sorted(e.opportunities, key=lambda o: -o.score)],
            "marketing_actions": [action(a) for a in e.marketing_actions if a.status not in ("DISMISSED_AUTO",)],
            "label": "RECOMMENDATION",
        },
    })
    return d


def opportunity(o: Opportunity, with_event: bool = False) -> dict:
    d = {"id": o.id, "event_id": o.event_id, "opportunity_type": o.opportunity_type, "score": o.score, "demand_level": o.demand_level,
         "window": {"start": o.window_start, "end": o.window_end, "label": o.window_label}, "reasons": o.reasons or [], "recommended_action": o.recommended_action,
         "score_components": o.score_components, "confidence": o.confidence}
    if with_event:
        d["event"] = event_summary(o.event)
    return d


def action(a: MarketingAction, with_event: bool = False) -> dict:
    d = {"id": a.id, "event_id": a.event_id, "action_type": a.action_type, "priority": a.priority, "title": a.title, "description": a.description,
         "suggested_keyword": a.suggested_keyword, "suggested_audience": a.suggested_audience, "suggested_channel": a.suggested_channel,
         "recommended_time": a.recommended_time, "recommended_date": a.recommended_date, "reason": a.reason, "status": a.status, "scheduled_for": a.scheduled_for.isoformat() if a.scheduled_for else None,
         "created_at": a.created_at.isoformat()}
    if with_event:
        d["event"] = {"id": a.event.id, "title": a.event.title, "date_start": a.event.date_start.isoformat(), "city": a.event.city.name if a.event.city else a.event.city_name_raw,
                      "venue": a.event.venue.name if a.event.venue else a.event.venue_name_raw, "score": a.event.opportunity_score}
    return d


def change(c: EventChange, with_event: bool = False) -> dict:
    d = {"id": c.id, "event_id": c.event_id, "change_type": c.change_type, "field": c.field, "old_value": c.old_value, "new_value": c.new_value, "detected_at": c.detected_at.isoformat()}
    if with_event:
        d["event"] = {"id": c.event.id, "title": c.event.title, "date_start": c.event.date_start.isoformat(), "city": c.event.city.name if c.event.city else c.event.city_name_raw}
    return d


def venue(v: Venue) -> dict:
    return {"id": v.id, "name": v.name, "city": v.city.name if v.city else None, "postcode": v.postcode, "latitude": v.latitude, "longitude": v.longitude,
            "capacity": v.capacity, "capacity_source": v.capacity_source, "venue_type": v.venue_type, "importance_score": v.importance_score,
            "station_distance_km": v.station_distance_km, "airport_distance_km": v.airport_distance_km, "is_seeded": v.is_seeded}


def source(s: Source) -> dict:
    reason = _disabled_reason(s)
    # A key-gated connector is DISABLED from the first moment (before any run), not UNKNOWN.
    status = "DISABLED" if (reason and reason.startswith("API key not configured")) or not s.enabled else s.status
    return {"id": s.id, "key": s.key, "name": s.name, "type": s.type, "enabled": s.enabled, "priority": s.priority, "status": status,
            "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None, "last_error": s.last_error,
            "last_response_ms": s.last_response_ms, "last_events_collected": s.last_events_collected,
            "requires_key": (s.config or {}).get("requires_key"),
            "disabled_reason": reason, "docs_url": (s.config or {}).get("docs_url"), "note": (s.config or {}).get("note"),
            "key_configured": _key_configured(s)}


def _key_configured(s: Source) -> bool | None:
    """True/False when the source needs a key (never exposes the value); None when no key is needed."""
    key = (s.config or {}).get("requires_key")
    if not key:
        return None
    from app.core.config import get_settings
    return bool(getattr(get_settings(), key.lower(), "") or "")


def _disabled_reason(s: Source) -> str | None:
    key = (s.config or {}).get("requires_key")
    if key and _key_configured(s) is False:
        return f"API key not configured ({key})"
    if not s.enabled:
        return "Disabled in settings"
    if s.status == "DISABLED":
        return s.last_error or "Disabled"
    return None
