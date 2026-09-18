from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.api.serializers import action, opportunity
from app.db.models import Event, MarketingAction, Opportunity
from app.schemas.api import ok

router = APIRouter(tags=["opportunities"])


@router.get("/opportunities")
def list_opportunities(db: Session = Depends(get_db), demand: str | None = None, days: int = Query(7, ge=1, le=90), opportunity_type: str | None = None,
                       city: str | None = None, page: int = 1, page_size: int = Query(50, le=500)):
    today = date.today()
    stmt = select(Opportunity).join(Event).where(Event.date_start >= today, Event.date_start <= today + timedelta(days=days), Event.status.in_(("SCHEDULED", "RESCHEDULED", "CONFIRMED", "SOLD_OUT")))
    if demand:
        stmt = stmt.where(Opportunity.demand_level.in_([d.strip().upper() for d in demand.split(",")]))
    if opportunity_type:
        stmt = stmt.where(Opportunity.opportunity_type == opportunity_type.upper())
    if city:
        stmt = stmt.where(Event.city_name_raw == city)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.options(selectinload(Opportunity.event).selectinload(Event.venue), selectinload(Opportunity.event).selectinload(Event.city))
                      .order_by(Opportunity.score.desc(), Event.date_start.asc()).offset((page - 1) * page_size).limit(page_size)).all()
    return ok([opportunity(o, with_event=True) for o in rows], {"page": page, "page_size": page_size, "total": total})


@router.get("/opportunities/{opp_id}")
def get_opportunity(opp_id: int, db: Session = Depends(get_db)):
    o = db.get(Opportunity, opp_id)
    if not o:
        raise HTTPException(404, detail={"code": "OPPORTUNITY_NOT_FOUND", "message": "Opportunity not found"})
    return ok(opportunity(o, with_event=True))


@router.get("/actions")
@router.get("/marketing-actions")
def list_actions(db: Session = Depends(get_db), status: str | None = Query(default="NEW,PLANNED,SCHEDULED,IN_PROGRESS"), days: int = Query(14, ge=1, le=90),
                 priority: str | None = None, action_type: str | None = None, city: str | None = None, q: str | None = None,
                 sort: str = Query("priority"), page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200)):
    today = date.today()
    stmt = select(MarketingAction).join(Event).where(Event.date_start >= today, Event.date_start <= today + timedelta(days=days))
    if status:
        stmt = stmt.where(MarketingAction.status.in_([s.strip().upper() for s in status.split(",")]))
    if priority:
        stmt = stmt.where(MarketingAction.priority == priority.upper())
    if action_type:
        stmt = stmt.where(MarketingAction.action_type.in_([a.strip().upper() for a in action_type.split(",")]))
    if city:
        stmt = stmt.where(Event.city_name_raw == city)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(MarketingAction.title.ilike(like) | Event.title.ilike(like) | Event.venue_name_raw.ilike(like))
    order = {"priority": (MarketingAction.priority.asc(), Event.date_start.asc(), Event.opportunity_score.desc()), "date": (Event.date_start.asc(),),
             "score": (Event.opportunity_score.desc(),), "created": (MarketingAction.created_at.desc(),)}.get(sort, (MarketingAction.priority.asc(),))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.options(selectinload(MarketingAction.event)).order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    return ok([action(a, with_event=True) for a in rows], {"page": page, "page_size": page_size, "total": total})


class ScheduleBody(BaseModel):
    scheduled_for: datetime


def _set_status(db: Session, action_id: int, status: str, scheduled_for: datetime | None = None) -> dict:
    a = db.get(MarketingAction, action_id)
    if not a:
        raise HTTPException(404, detail={"code": "ACTION_NOT_FOUND", "message": "Action not found"})
    a.status = status
    if scheduled_for:
        a.scheduled_for = scheduled_for
    db.commit()
    return ok(action(a, with_event=True))


@router.get("/marketing-actions/{action_id}")
def get_marketing_action(action_id: int, db: Session = Depends(get_db)):
    a = db.get(MarketingAction, action_id)
    if not a:
        raise HTTPException(404, detail={"code": "ACTION_NOT_FOUND", "message": "Marketing action not found"})
    return ok(action(a, with_event=True))


@router.post("/actions/{action_id}/complete")
def complete_action(action_id: int, db: Session = Depends(get_db)):
    return _set_status(db, action_id, "DONE")


@router.post("/actions/{action_id}/dismiss")
def dismiss_action(action_id: int, db: Session = Depends(get_db)):
    return _set_status(db, action_id, "DISMISSED")


@router.post("/actions/{action_id}/schedule")
def schedule_action(action_id: int, body: ScheduleBody, db: Session = Depends(get_db)):
    """SCHEDULED = a concrete date/time is set. PLANNED (see /plan) = intent without a slot."""
    return _set_status(db, action_id, "SCHEDULED", body.scheduled_for)


@router.post("/actions/{action_id}/plan")
def plan_action(action_id: int, db: Session = Depends(get_db)):
    return _set_status(db, action_id, "PLANNED")


@router.post("/actions/{action_id}/reopen")
def reopen_action(action_id: int, db: Session = Depends(get_db)):
    return _set_status(db, action_id, "NEW")


@router.post("/actions/{action_id}/start")
def start_action(action_id: int, db: Session = Depends(get_db)):
    return _set_status(db, action_id, "IN_PROGRESS")
