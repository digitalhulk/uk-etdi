from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.api.serializers import event_summary
from app.db.models import City, Event, EventChange, PipelineRun, Region, Source, Venue
from app.orchestration.reports import build_daily_report, summary_counts, top_events
from app.schemas.api import ok

router = APIRouter(tags=["dashboard"])
ACTIVE = ("SCHEDULED", "RESCHEDULED", "CONFIRMED", "SOLD_OUT")  # live statuses (single source of truth: reports.ACTIVE)


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    s = summary_counts(db)
    last = db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)).first()
    s["last_pipeline_run"] = {"id": last.id, "status": last.status, "completed_at": last.completed_at.isoformat() if last.completed_at else None,
                              "duration_seconds": last.duration_seconds} if last else None
    s["top_opportunities"] = [event_summary(e) for e in top_events(db, limit=5)]
    return ok(s)


@router.get("/dashboard/map")
def dashboard_map(db: Session = Depends(get_db), days: int = Query(7, ge=0, le=90), min_score: int = 0):
    today = date.today()
    rows = db.scalars(select(Event).options(selectinload(Event.venue), selectinload(Event.city))
                      .where(Event.date_start >= today, Event.date_start <= today + timedelta(days=days), Event.status.in_(ACTIVE),
                             Event.latitude.isnot(None), Event.opportunity_score >= min_score).order_by(Event.opportunity_score.desc())).all()
    from app.providers import get_map_provider
    return ok([{"id": e.id, "title": e.title, "lat": e.latitude, "lon": e.longitude, "score": e.opportunity_score, "demand_level": e.demand_level,
                "date": e.date_start.isoformat(), "time": e.time_start, "venue": e.venue.name if e.venue else e.venue_name_raw,
                "city": e.city.name if e.city else e.city_name_raw, "category": e.category, "marketing_priority": e.marketing_priority} for e in rows],
              {"total": len(rows), "days": days, "tiles": get_map_provider().tile_config()})


@router.get("/dashboard/trends")
def dashboard_trends(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=120)):
    today = date.today()
    horizon = today + timedelta(days=days)
    upcoming = (Event.date_start >= today, Event.date_start <= horizon, Event.status.in_(ACTIVE))

    def grouped(col, label, limit=None, extra=()):
        stmt = select(col.label("key"), func.count(Event.id).label("count"), func.avg(Event.opportunity_score).label("avg_score")).where(*upcoming, *extra).group_by(col).order_by(func.count(Event.id).desc())
        if limit:
            stmt = stmt.limit(limit)
        return [{label: r.key, "count": r.count, "avg_score": round(r.avg_score or 0, 1)} for r in db.execute(stmt).all()]

    by_city = db.execute(select(City.name, func.count(Event.id), func.avg(Event.opportunity_score)).join(Event, Event.city_id == City.id).where(*upcoming).group_by(City.name).order_by(func.count(Event.id).desc()).limit(15)).all()
    by_region = db.execute(select(Region.name, func.count(Event.id)).join(Event, Event.region_id == Region.id).where(*upcoming).group_by(Region.name).order_by(func.count(Event.id).desc())).all()
    top_venues = db.execute(select(Venue.name, func.count(Event.id), func.max(Event.opportunity_score)).join(Event, Event.venue_id == Venue.id).where(*upcoming).group_by(Venue.name).order_by(func.count(Event.id).desc()).limit(10)).all()
    by_day = db.execute(select(Event.date_start, func.count(Event.id), func.sum(case((Event.demand_level.in_(("HIGH", "VERY_HIGH")), 1), else_=0))).where(*upcoming).group_by(Event.date_start).order_by(Event.date_start)).all()
    buckets = case((Event.opportunity_score >= 80, "80-100"), (Event.opportunity_score >= 65, "65-79"), (Event.opportunity_score >= 50, "50-64"), (Event.opportunity_score >= 35, "35-49"), else_="0-34")
    dist = db.execute(select(buckets, func.count(Event.id)).where(*upcoming).group_by(buckets)).all()
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=14)
    new_trend = db.execute(select(func.date(EventChange.detected_at), func.count(EventChange.id)).where(EventChange.change_type == "NEW", EventChange.detected_at >= since).group_by(func.date(EventChange.detected_at)).order_by(func.date(EventChange.detected_at))).all()
    change_trend = db.execute(select(func.date(EventChange.detected_at), EventChange.change_type, func.count(EventChange.id)).where(EventChange.detected_at >= since).group_by(func.date(EventChange.detected_at), EventChange.change_type)).all()
    coverage = db.execute(select(Event.primary_source, func.count(Event.id)).where(*upcoming).group_by(Event.primary_source)).all()
    return ok({
        "horizon_days": days,
        "by_category": grouped(Event.category, "category"),
        "by_city": [{"city": n, "count": c, "avg_score": round(a or 0, 1)} for n, c, a in by_city],
        "by_region": [{"region": n, "count": c} for n, c in by_region],
        "by_day": [{"date": d.isoformat(), "count": c, "high_or_above": int(h or 0)} for d, c, h in by_day],
        "score_distribution": [{"bucket": b, "count": c} for b, c in dist],
        "top_venues": [{"venue": n, "count": c, "max_score": m} for n, c, m in top_venues],
        "source_coverage": [{"source": s, "count": c} for s, c in coverage],
        "new_events_trend": [{"date": str(d), "count": c} for d, c in new_trend],
        "change_trend": [{"date": str(d), "change_type": t, "count": c} for d, t, c in change_trend],
    })


@router.get("/dashboard/calendar")
@router.get("/calendar", include_in_schema=False)
def calendar(db: Session = Depends(get_db), start: date = Query(...), end: date = Query(...)):
    rows = db.scalars(select(Event).options(selectinload(Event.venue), selectinload(Event.city)).where(Event.date_start <= end, func.coalesce(Event.date_end, Event.date_start) >= start)
                      .order_by(Event.date_start, Event.time_start)).all()
    return ok([event_summary(e) for e in rows], {"total": len(rows)})


@router.get("/reports/daily")
def daily_report(db: Session = Depends(get_db)):
    return ok(build_daily_report(db))
