"""CSV / JSON exports (section 59) — streamed from DB-level queries; identical filters to the list endpoints."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.api.routes.events import apply_filters
from app.api.serializers import action, event_summary, opportunity
from app.db.models import Event, MarketingAction, Opportunity, PipelineRun

router = APIRouter(tags=["exports"])
MAX_ROWS = 20000


def _flatten(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out[f"{k}_{k2}"] = v2 if not isinstance(v2, (dict, list)) else json.dumps(v2, default=str)
        elif isinstance(v, list):
            out[k] = json.dumps(v, default=str)
        else:
            out[k] = v
    return out


def _stream(rows: Iterable[dict], fmt: str, name: str) -> StreamingResponse:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    if fmt == "json":
        def gen_json():
            yield "["
            first = True
            for r in rows:
                yield ("" if first else ",") + json.dumps(r, default=str)
                first = False
            yield "]"
        return StreamingResponse(gen_json(), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}-{stamp}.json"'})

    def gen_csv():
        buf = io.StringIO()
        writer = None
        for r in rows:
            flat = _flatten(r)
            if writer is None:
                writer = csv.DictWriter(buf, fieldnames=list(flat.keys()), extrasaction="ignore")
                writer.writeheader()
            writer.writerow(flat)
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)
        if writer is None:
            yield ""
    return StreamingResponse(gen_csv(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}-{stamp}.csv"'})


def _fmt(fmt: str) -> str:
    if fmt not in ("csv", "json"):
        raise HTTPException(400, detail={"code": "BAD_FORMAT", "message": "format must be csv or json"})
    return fmt


@router.get("/export/events")
def export_events(db: Session = Depends(get_db), format: str = Query("csv"), range: str | None = None, date_from: date | None = None, date_to: date | None = None,
                  category: str | None = None, city: str | None = None, region: str | None = None, status: str | None = None, source: str | None = None,
                  quality: str | None = None, confidence: str | None = None, min_score: int | None = None, q: str | None = None):
    fmt = _fmt(format)
    stmt = apply_filters(select(Event).options(selectinload(Event.venue), selectinload(Event.city)), range_=range, date_from=date_from, date_to=date_to,
                         category=category, city=city, region=region, demand=None, min_score=min_score, venue=None, status=status, source=source, q=q,
                         quality=quality, confidence=confidence, subcategory=None, missing=None).order_by(Event.date_start).limit(MAX_ROWS)
    return _stream((event_summary(e) for e in db.scalars(stmt)), fmt, "events")


@router.get("/export/opportunities")
def export_opportunities(db: Session = Depends(get_db), format: str = Query("csv"), min_score: int = 0, days: int = Query(30, ge=0, le=365)):
    fmt = _fmt(format)
    from datetime import timedelta
    today = date.today()
    stmt = (select(Opportunity).join(Event).options(selectinload(Opportunity.event))
            .where(Opportunity.score >= min_score, Event.date_start >= today, Event.date_start <= today + timedelta(days=days))
            .order_by(Opportunity.score.desc()).limit(MAX_ROWS))
    return _stream((opportunity(o) for o in db.scalars(stmt)), fmt, "opportunities")


@router.get("/export/marketing-actions")
@router.get("/export/actions", include_in_schema=False)
def export_actions(db: Session = Depends(get_db), format: str = Query("csv"), status: str | None = None, action_type: str | None = None):
    fmt = _fmt(format)
    stmt = select(MarketingAction).options(selectinload(MarketingAction.event)).order_by(MarketingAction.priority.desc(), MarketingAction.id.desc())
    if status:
        stmt = stmt.where(MarketingAction.status == status.upper())
    if action_type:
        stmt = stmt.where(MarketingAction.action_type == action_type.upper())
    return _stream((action(a) for a in db.scalars(stmt.limit(MAX_ROWS))), fmt, "marketing-actions")


@router.get("/export/reports")
def export_reports(db: Session = Depends(get_db), format: str = Query("csv"), limit: int = Query(90, ge=1, le=1000)):
    """Pipeline run reports (one row per run)."""
    fmt = _fmt(format)
    cols = ("id", "trigger", "status", "started_at", "completed_at", "duration_seconds", "sources_attempted", "sources_successful", "sources_failed",
            "events_raw", "events_valid", "events_created", "events_updated", "duplicates_removed", "changes_detected", "opportunities_generated", "actions_generated")
    rows = ({c: getattr(r, c, None) for c in cols} for r in db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit)))
    return _stream(rows, fmt, "pipeline-reports")
