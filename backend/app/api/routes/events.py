from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.api.serializers import change, event_detail, event_summary
from app.db.models import City, Event, EventChange, Region, Venue
from app.schemas.api import ok

router = APIRouter(tags=["events"])

RANGES = {"today": 0, "tomorrow": 1, "7d": 7, "30d": 30}


def apply_filters(stmt, *, range_: str | None, date_from: date | None, date_to: date | None, category, city, region, demand, min_score, venue, status, source, q,
                  quality: str | None = None, confidence: str | None = None, subcategory: str | None = None, missing: str | None = None):
    today = date.today()
    if range_ in RANGES:
        if range_ == "tomorrow":
            stmt = stmt.where(Event.date_start <= today + timedelta(days=1), func.coalesce(Event.date_end, Event.date_start) >= today + timedelta(days=1))
        elif range_ == "today":
            stmt = stmt.where(Event.date_start <= today, func.coalesce(Event.date_end, Event.date_start) >= today)
        else:
            stmt = stmt.where(Event.date_start >= today, Event.date_start <= today + timedelta(days=RANGES[range_]))
    if date_from:
        stmt = stmt.where(Event.date_start >= date_from)
    if date_to:
        stmt = stmt.where(Event.date_start <= date_to)
    if category:
        stmt = stmt.where(Event.category == category)
    if city:
        stmt = stmt.join(City, City.id == Event.city_id, isouter=True).where(or_(City.name == city, Event.city_name_raw == city))
    if region:
        stmt = stmt.join(Region, Region.id == Event.region_id).where(Region.name == region)
    if demand:
        stmt = stmt.where(Event.demand_level.in_([d.strip().upper() for d in demand.split(",")]))
    if min_score is not None:
        stmt = stmt.where(Event.opportunity_score >= min_score)
    if venue:
        stmt = stmt.join(Venue, Venue.id == Event.venue_id, isouter=True).where(or_(Venue.name.ilike(f"%{venue}%"), Event.venue_name_raw.ilike(f"%{venue}%")))
    if status:
        stmt = stmt.where(Event.status == status.upper())
    if source:
        stmt = stmt.where(Event.primary_source == source)
    if q:
        like = f"%{q}%"
        stmt = stmt.outerjoin(Venue, Venue.id == Event.venue_id).where(or_(Event.title.ilike(like), Event.city_name_raw.ilike(like), Event.venue_name_raw.ilike(like), Venue.name.ilike(like)))
    if quality:
        stmt = stmt.where(Event.quality_level.in_([x.strip().upper() for x in quality.split(",")]))
    if confidence:
        stmt = stmt.where(Event.source_confidence.in_([x.strip().upper() for x in confidence.split(",")]))
    if subcategory:
        stmt = stmt.where(Event.subcategory == subcategory)
    for m in [x.strip() for x in (missing or "").split(",") if x.strip()]:  # Data Quality drill-through
        col = {"time": Event.time_start.is_(None), "venue": Event.venue_id.is_(None), "location": Event.city_id.is_(None),
               "official_url": and_(Event.official_url.is_(None), Event.ticket_url.is_(None)), "coordinates": Event.latitude.is_(None),
               "capacity": Event.venue_capacity.is_(None)}.get(m)
        if col is not None:
            stmt = stmt.where(col)
    return stmt


@router.get("/events")
def list_events(db: Session = Depends(get_db), range: str | None = Query(default=None, alias="range"), date_from: date | None = None, date_to: date | None = None,
                category: str | None = None, city: str | None = None, region: str | None = None, demand: str | None = None, min_score: int | None = None,
                venue: str | None = None, status: str | None = None, source: str | None = None, q: str | None = None,
                quality: str | None = None, confidence: str | None = None, subcategory: str | None = None, missing: str | None = None,
                sort: str = Query(default="score"), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = apply_filters(select(Event), range_=range, date_from=date_from, date_to=date_to, category=category, city=city, region=region, demand=demand,
                         min_score=min_score, venue=venue, status=status, source=source, q=q, quality=quality, confidence=confidence, subcategory=subcategory, missing=missing)
    if range is None and date_from is None and date_to is None:
        stmt = stmt.where(Event.date_start >= date.today())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {"score": (Event.opportunity_score.desc(), Event.date_start.asc()), "date": (Event.date_start.asc(), Event.time_start.asc()),
             "updated": (Event.last_updated_at.desc(),), "quality": (Event.event_quality_score.desc(), Event.opportunity_score.desc())}.get(sort, (Event.opportunity_score.desc(),))
    rows = db.scalars(stmt.options(selectinload(Event.venue), selectinload(Event.city), selectinload(Event.region)).order_by(*order)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return ok([event_summary(e) for e in rows], {"page": page, "page_size": page_size, "total": total})


@router.get("/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    e = db.get(Event, event_id)
    if not e:
        raise HTTPException(404, detail={"code": "EVENT_NOT_FOUND", "message": "Event not found"})
    return ok(event_detail(e))


@router.get("/changes")
def list_changes(db: Session = Depends(get_db), days: int = Query(7, ge=1, le=90), change_type: str | None = None, page: int = 1, page_size: int = Query(100, le=500)):
    from app.db.models import utcnow
    since = utcnow() - timedelta(days=days)
    stmt = select(EventChange).where(EventChange.detected_at >= since)
    if change_type:
        stmt = stmt.where(EventChange.change_type == change_type.upper())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.options(selectinload(EventChange.event)).order_by(EventChange.detected_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return ok([change(c, with_event=True) for c in rows], {"page": page, "page_size": page_size, "total": total})
