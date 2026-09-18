"""Pipeline idempotency + change detection using an in-memory fake collector (no network)."""
from datetime import date, timedelta

from sqlalchemy import func, select

from app.collectors.base import CollectResult
from app.db.models import Event, EventChange, MarketingAction, Opportunity
from app.orchestration import pipeline as pl
from app.schemas.normalized import NormalizedEvent

D = date.today() + timedelta(days=5)


def _events(status="SCHEDULED", time_start="19:30", title="Big Concert Tour"):
    return [
        NormalizedEvent(source_key="curated", external_id="x1", title=title, category_hint="concert", date_start=D, time_start=time_start,
                        venue_name="The O2", city_name="London", status=status, raw={"id": "x1", "t": title, "s": status, "ts": time_start}),
        NormalizedEvent(source_key="curated", external_id="x2", title="Arsenal v Chelsea", date_start=D, time_start="15:00",
                        venue_name="Emirates Stadium", city_name="London", raw={"id": "x2"}),
        # duplicate of x2 from another id -> fingerprint dedupe
        NormalizedEvent(source_key="curated", external_id="x3", title="Arsenal v Chelsea", date_start=D, time_start="15:00",
                        venue_name="Emirates Stadium", city_name="London", raw={"id": "x3"}),
    ]


class FakeCollector:
    name = "curated"

    def __init__(self, events):
        self._events = events

    def run(self):
        return CollectResult("curated", events=self._events)


def _run(db, monkeypatch, events):
    monkeypatch.setattr(pl, "build_collectors", lambda only=None: [FakeCollector(events)])
    return pl.run_pipeline(db, trigger="test", notify=False)


def test_pipeline_idempotent_and_detects_changes(db_session, monkeypatch):
    db = db_session
    r1 = _run(db, monkeypatch, _events())
    assert r1.status == "SUCCESS"
    assert r1.events_created == 2 and r1.duplicates_removed == 1
    n1 = db.scalar(select(func.count(Event.id)))

    r2 = _run(db, monkeypatch, _events())
    assert r2.events_created == 0 and r2.changes_detected == 0
    assert db.scalar(select(func.count(Event.id))) == n1

    r3 = _run(db, monkeypatch, _events(time_start="20:00", status="CANCELLED"))
    types = {c.change_type for c in db.scalars(select(EventChange).where(EventChange.pipeline_run_id == r3.id))}
    assert {"TIME_CHANGED", "CANCELLED"} <= types
    ev = db.scalar(select(Event).where(Event.title == "Big Concert Tour"))
    assert ev.status == "CANCELLED" and ev.opportunity_score == 0
    assert all(a.status == "DISMISSED" for a in ev.marketing_actions)

    arsenal = db.scalar(select(Event).where(Event.title == "Arsenal v Chelsea"))
    assert arsenal.venue.capacity == 60704 and arsenal.city.name == "London"
    assert arsenal.opportunity_score > 60
    assert db.scalar(select(func.count(Opportunity.id)).where(Opportunity.event_id == arsenal.id)) >= 5
    assert db.scalar(select(func.count(MarketingAction.id)).where(MarketingAction.event_id == arsenal.id)) >= 5
    assert arsenal.demand_windows["label"] == "Modelled demand window"
