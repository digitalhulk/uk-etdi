from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import require_admin
from app.db.models import PipelineRun
from app.schemas.api import ok

router = APIRouter(tags=["pipeline"])
_lock = threading.Lock()


def _run_bg(only: list[str] | None, notify: bool):
    from app.orchestration.jobs import job_pipeline
    with _lock:
        job_pipeline(trigger="api", only=only, notify=notify)


@router.post("/pipeline/run", dependencies=[Depends(require_admin)])
def run_pipeline_endpoint(sources: str | None = Query(default=None, description="comma-separated source keys"), notify: bool = True, sync: bool = False):
    only = [s.strip() for s in sources.split(",")] if sources else None
    if _lock.locked():
        return ok({"queued": False, "message": "pipeline already running"})
    if sync:
        _run_bg(only, notify)
        return ok({"queued": False, "message": "pipeline completed"})
    threading.Thread(target=_run_bg, args=(only, notify), daemon=True).start()
    return ok({"queued": True, "message": "pipeline started in background"})


@router.get("/pipeline/runs")
def pipeline_runs(db: Session = Depends(get_db), limit: int = Query(20, le=200)):
    rows = db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit)).all()
    return ok([{k: getattr(r, k) for k in ("id", "trigger", "status", "started_at", "completed_at", "duration_seconds", "sources_attempted", "sources_successful",
               "sources_failed", "events_raw", "events_valid", "events_created", "events_updated", "duplicates_removed", "changes_detected", "notifications_sent", "errors")} for r in rows])
