from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.serializers import venue as ser_venue
from app.db.models import Event, Venue
from app.schemas.api import ok

router = APIRouter(tags=["venues"])


@router.get("/venues")
def list_venues(db: Session = Depends(get_db), q: str | None = None, seeded_only: bool = False, page: int = 1, page_size: int = Query(100, le=500)):
    stmt = select(Venue, func.count(Event.id).label("upcoming")).outerjoin(Event, (Event.venue_id == Venue.id) & (Event.date_start >= func.current_date())).group_by(Venue.id)
    if q:
        stmt = stmt.where(Venue.name.ilike(f"%{q}%"))
    if seeded_only:
        stmt = stmt.where(Venue.is_seeded.is_(True))
    total = db.scalar(select(func.count(Venue.id)).where(Venue.name.ilike(f"%{q}%") if q else True)) or 0
    rows = db.execute(stmt.order_by(func.count(Event.id).desc(), Venue.capacity.desc().nullslast()).offset((page - 1) * page_size).limit(page_size)).all()
    return ok([{**ser_venue(v), "upcoming_events": n} for v, n in rows], {"page": page, "page_size": page_size, "total": total})
