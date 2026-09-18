from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models import ErrorLog, Event, Notification, PipelineRun, RawEvent, Source, SystemHealth
from app.schemas.api import ok

from app.providers.registry import providers_status


def _scheduler_running() -> bool:
    try:
        from app.orchestration import scheduler
        return bool(getattr(scheduler, "_thread", None) and scheduler._thread.is_alive())
    except Exception:
        return False


def _next_cron_run() -> str | None:
    """Next run of the GitHub Actions daily cron (06:00 UTC by default, see .github/workflows/daily-pipeline.yml)."""
    from datetime import datetime, timedelta, timezone
    import os
    hour = int(os.getenv("PIPELINE_CRON_HOUR_UTC", "6"))
    now = datetime.now(timezone.utc)
    nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return nxt.isoformat()


router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "HEALTHY"
    except Exception:
        db_status = "FAILED"
    return ok({"status": "ok" if db_status == "HEALTHY" else "degraded", "database": db_status, "app": get_settings().app_name, "env": get_settings().app_env})


@router.get("/health/detailed")
def health_detailed(db: Session = Depends(get_db)):
    last = db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)).first()
    runs = db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(10)).all()
    errors = db.scalars(select(ErrorLog).order_by(ErrorLog.id.desc()).limit(20)).all()
    sources = db.scalars(select(Source)).all()
    s = get_settings()
    return ok({
        "database": {"status": "HEALTHY", "url_scheme": s.database_url.split(":")[0], "events": db.scalar(select(func.count(Event.id))), "raw_events": db.scalar(select(func.count(RawEvent.id)))},
        "last_pipeline_run": {k: getattr(last, k) for k in ("id", "trigger", "status", "started_at", "completed_at", "duration_seconds", "sources_attempted", "sources_successful", "sources_failed",
                              "events_raw", "events_valid", "events_created", "events_updated", "duplicates_removed", "changes_detected", "opportunities_generated", "actions_generated",
                              "notifications_sent", "errors", "stages")} if last else None,
        "recent_runs": [{"id": r.id, "status": r.status, "started_at": r.started_at.isoformat(), "duration_seconds": r.duration_seconds, "events_valid": r.events_valid,
                         "events_created": r.events_created, "changes_detected": r.changes_detected} for r in runs],
        "sources": {"total": len(sources), "healthy": sum(1 for x in sources if x.status == "HEALTHY"), "degraded": sum(1 for x in sources if x.status == "DEGRADED"),
                    "failed": sum(1 for x in sources if x.status == "FAILED"), "disabled": sum(1 for x in sources if x.status == "DISABLED" or not x.enabled)},
        "notifications": {"sent": db.scalar(select(func.count(Notification.id)).where(Notification.status == "SENT")), "failed": db.scalar(select(func.count(Notification.id)).where(Notification.status == "FAILED")),
                          "telegram_configured": bool(s.telegram_bot_token and s.telegram_chat_id), "sheets_configured": bool(s.google_sheets_webhook)},
        "providers": providers_status(),
        "scheduler": {"mode": "github_actions_cron" if not getattr(s, "scheduler_enabled", False) else "in_process", "in_process_running": _scheduler_running(),
                      "next_scheduled_run": _next_cron_run()},
        "recent_errors": [{"id": e.id, "at": e.occurred_at.isoformat(), "component": e.component, "message": e.message[:300]} for e in errors],
        "components": [{"component": h.component, "status": h.status, "recorded_at": h.recorded_at.isoformat()} for h in
                       db.scalars(select(SystemHealth).order_by(SystemHealth.id.desc()).limit(20)).all()],
    })
