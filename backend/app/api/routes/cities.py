from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Category, City, Event, Region
from app.schemas.api import ok

router = APIRouter(tags=["cities"])


@router.get("/cities")
def list_cities(db: Session = Depends(get_db)):
    rows = db.execute(select(City, Region.name, func.count(Event.id)).outerjoin(Region, Region.id == City.region_id)
                      .outerjoin(Event, (Event.city_id == City.id) & (Event.date_start >= func.current_date())).group_by(City.id).order_by(City.priority.desc())).all()
    return ok([{"id": c.id, "name": c.name, "region": r, "country": c.country, "latitude": c.latitude, "longitude": c.longitude, "population": c.population,
                "population_source": c.population_source, "priority": c.priority, "tourism": c.tourism, "upcoming_events": n} for c, r, n in rows])


@router.get("/regions")
def list_regions(db: Session = Depends(get_db)):
    rows = db.execute(select(Region, func.count(Event.id)).outerjoin(Event, (Event.region_id == Region.id) & (Event.date_start >= func.current_date())).group_by(Region.id)).all()
    return ok([{"id": r.id, "name": r.name, "country": r.country, "upcoming_events": n} for r, n in rows])


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    rows = db.execute(select(Event.category, Event.subcategory, func.count(Event.id)).where(Event.date_start >= func.current_date()).group_by(Event.category, Event.subcategory)).all()
    cats = db.scalars(select(Category)).all()
    counts = {(c, s): n for c, s, n in rows}
    return ok([{"category": c.name, "subcategory": c.subcategory, "upcoming_events": counts.get((c.name, c.subcategory), 0)} for c in cats])
