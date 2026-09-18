"""Coverage / data-quality / source drilldown endpoints (Phase 2). All numbers are computed from DB + config."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.api.serializers import event_summary
from app.db.models import Event, EventSnapshot, EventSource, Source, SourceRun
from app.intelligence.coverage import coverage_report, data_quality_report, source_health
from app.schemas.api import ok

router = APIRouter(tags=["coverage"])


@router.get("/coverage")
def coverage(db: Session = Depends(get_db)):
    return ok(coverage_report(db))


@router.get("/coverage/sources")
def coverage_sources(db: Session = Depends(get_db)):
    return ok(source_health(db))


@router.get("/data-quality")
def data_quality(db: Session = Depends(get_db)):
    return ok(data_quality_report(db))


@router.get("/sources/{source_id}/events")
def source_events(source_id: int, db: Session = Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    """Source drilldown: events currently linked to this source (future first)."""
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found"})
    base = select(Event).join(EventSource, EventSource.event_id == Event.id).where(EventSource.source_id == s.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.options(selectinload(Event.venue), selectinload(Event.city), selectinload(Event.region))
                      .order_by(Event.date_start.asc()).offset((page - 1) * page_size).limit(page_size)).all()
    runs = db.scalars(select(SourceRun).where(SourceRun.source_id == s.id).order_by(SourceRun.id.desc()).limit(30)).all()
    return ok({"source": {"id": s.id, "key": s.key, "status": s.status}, "events": [event_summary(e) for e in rows],
               "runs": [{"id": r.id, "started_at": r.started_at.isoformat(), "status": r.status, "events": r.events_collected, "response_ms": r.response_ms,
                         "error": r.error} for r in runs]},
              {"page": page, "page_size": page_size, "total": total})


@router.get("/events/{event_id}/snapshots")
def event_snapshots(event_id: int, db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100)):
    rows = db.scalars(select(EventSnapshot).where(EventSnapshot.event_id == event_id).order_by(EventSnapshot.id.desc()).limit(limit)).all()
    return ok([{"id": r.id, "taken_at": r.taken_at.isoformat(), "reason": r.reason, "pipeline_run_id": r.pipeline_run_id, "snapshot": r.snapshot} for r in rows])
