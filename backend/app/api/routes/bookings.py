"""Historical taxi bookings: upload (admin), status, correlation and forecast-mode endpoints (sections 31–33)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.bookings import correlate as corr
from app.bookings import features as feat
from app.bookings import ingest
from app.core.security import require_admin
from app.db.models import EventBookingCorrelation, TaxiBooking
from app.schemas.api import ok

router = APIRouter(tags=["bookings"])


@router.get("/bookings/status")
def bookings_status(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(TaxiBooking.id))) or 0
    first = db.scalar(select(func.min(TaxiBooking.pickup_datetime)))
    last = db.scalar(select(func.max(TaxiBooking.pickup_datetime)))
    mode, info = feat.forecast_mode(db)
    return ok({"bookings": total, "first_pickup": first.isoformat() if first else None, "last_pickup": last.isoformat() if last else None,
               "correlations": db.scalar(select(func.count(EventBookingCorrelation.id))) or 0, "model_mode": mode, **info,
               "note": "Correlation is spatial-temporal only and is never treated as causation. Demand stays MODELLED until FORECAST mode."})


@router.post("/bookings/upload", dependencies=[Depends(require_admin)])
async def upload_bookings(file: UploadFile = File(...), db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".csv", ".json", ".xlsx"):
        raise HTTPException(400, detail={"code": "BAD_FILE", "message": "Upload a .csv, .json or .xlsx file"})
    data = await file.read()
    if len(data) > 50_000_000:
        raise HTTPException(413, detail={"code": "TOO_LARGE", "message": "File exceeds 50 MB"})
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        stats = ingest.ingest(db, ingest.read_path(path), source_label=file.filename)
    finally:
        Path(path).unlink(missing_ok=True)
    return ok(stats)


@router.post("/bookings/correlate", dependencies=[Depends(require_admin)])
def run_correlation(db: Session = Depends(get_db)):
    stats = corr.correlate(db)
    stats["features"] = feat.refresh_features(db)
    return ok(stats)


@router.get("/bookings/correlations")
def list_correlations(db: Session = Depends(get_db), event_id: int | None = None, page: int = 1, page_size: int = 50):
    page_size = min(max(page_size, 1), 200)
    stmt = select(EventBookingCorrelation)
    if event_id:
        stmt = stmt.where(EventBookingCorrelation.event_id == event_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(EventBookingCorrelation.match_confidence.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return ok([{"id": r.id, "event_id": r.event_id, "booking_id": r.booking_id, "leg": r.leg, "distance_km": r.distance_km, "time_delta_min": r.time_delta_min,
                "match_confidence": r.match_confidence, "method": r.method} for r in rows], {"page": page, "page_size": page_size, "total": total})
