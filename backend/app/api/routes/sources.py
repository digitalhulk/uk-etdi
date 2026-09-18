from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.serializers import source
from app.collectors.registry import COLLECTORS
from app.core.config import sources_config
from app.core.security import require_admin
from app.db.models import Source, SourceRun
from app.schemas.api import ok

router = APIRouter(tags=["sources"])


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    rows = db.scalars(select(Source).order_by(Source.priority.desc())).all()
    return ok([source(s) for s in rows])


@router.get("/sources/{source_id}")
def get_source(source_id: int, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found"})
    runs = db.scalars(select(SourceRun).where(SourceRun.source_id == s.id).order_by(SourceRun.id.desc()).limit(30)).all()
    cfg = {k: v for k, v in (sources_config().get(s.key, {}) or {}).items() if "key" not in k.lower() or k == "requires_key"}  # config without secrets
    return ok({**source(s), "config": cfg,
               "recent_runs": [{"id": r.id, "started_at": r.started_at.isoformat(), "status": r.status, "events": r.events_collected, "response_ms": r.response_ms, "error": r.error} for r in runs]})


@router.get("/sources/{source_id}/health")
def source_health(source_id: int, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found"})
    runs = db.scalars(select(SourceRun).where(SourceRun.source_id == s.id).order_by(SourceRun.id.desc()).limit(20)).all()
    live = None
    cls = COLLECTORS.get(s.key)
    if cls:
        inst = cls(sources_config().get(s.key, {})); inst.name = s.key
        h = inst.health_check()
        live = {"status": h.status, "message": h.message, "response_ms": h.response_ms}
    return ok({**source(s), "live_check": live,
               "recent_runs": [{"id": r.id, "started_at": r.started_at.isoformat(), "status": r.status, "events": r.events_collected, "response_ms": r.response_ms, "error": r.error} for r in runs]})


@router.post("/sources/{source_id}/toggle", dependencies=[Depends(require_admin)])
def toggle_source(source_id: int, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found"})
    s.enabled = not s.enabled
    if not s.enabled:
        s.status = "DISABLED"
    db.commit()
    return ok(source(s))
