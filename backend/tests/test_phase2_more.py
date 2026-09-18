"""§41: date parsing / BST-GMT, multi-day, dedupe & fuzzy, digest formatting, pagination & filters, DB constraints, recovery, zero-result source."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.collectors.venue import parse_schema_datetime
from app.processors.deduplicate import fingerprint, similarity
from app.processors.normalize import parse_uk_date, split_local
from app.orchestration.reports import format_daily_digest


def test_schema_datetime_variants():
    assert parse_schema_datetime("2026-09-22T12:00") == (date(2026, 9, 22), "12:00")               # naive → local
    assert parse_schema_datetime("2026-07-01T19:30:00+01:00") == (date(2026, 7, 1), "19:30")       # BST offset kept local
    assert parse_schema_datetime("2026-07-01T18:30:00Z") == (date(2026, 7, 1), "19:30")            # UTC → BST
    assert parse_schema_datetime("2026-12-01T18:30:00Z") == (date(2026, 12, 1), "18:30")           # UTC → GMT
    assert parse_schema_datetime("2026-09-22 14:00:00")[1] == "14:00"                             # tribe space separator
    assert parse_schema_datetime("2026-09-22") == (date(2026, 9, 22), None)
    assert parse_schema_datetime(None) == (None, None) and parse_schema_datetime("garbage")[0] is None


def test_bst_gmt_split_local():
    assert split_local(datetime(2026, 8, 15, 14, 0)) == (date(2026, 8, 15), "15:00")
    assert split_local(datetime(2026, 1, 15, 14, 0)) == (date(2026, 1, 15), "14:00")
    assert split_local(datetime(2026, 8, 15, 23, 30)) == (date(2026, 8, 16), "00:30")  # crosses midnight in BST


def test_uk_date_parsing():
    assert parse_uk_date("22/09/2026") == date(2026, 9, 22)
    assert parse_uk_date("22 Sep 2026") == date(2026, 9, 22)


def test_fingerprint_and_fuzzy_similarity():
    a = fingerprint("Arsenal v Chelsea", date(2026, 10, 1), "Emirates Stadium", "London")
    b = fingerprint("Arsenal v Chelsea", date(2026, 10, 1), "Emirates Stadium", "London")
    c = fingerprint("Arsenal v Chelsea", date(2026, 10, 2), "Emirates Stadium", "London")
    assert a == b != c
    conf, _ = similarity("Arsenal v Chelsea", "Arsenal vs Chelsea", "Emirates Stadium", "Emirates", "London", "London", True)
    assert conf >= 0.8
    conf2, _ = similarity("Arsenal v Chelsea", "Coldplay Live", "Emirates Stadium", "Wembley", "London", "London", True)
    assert conf2 < 0.6


def test_multi_day_event_normalizes_end_date():
    from app.collectors.venue import VenuePageCollector
    c = VenuePageCollector({})
    ev = c.normalize({"@type": "Festival", "name": "Big Fest", "startDate": "2027-06-04T12:00", "endDate": "2027-06-06T23:00", "_page": {"venue": "Field", "city": "Leeds", "url": "https://x.example/"}})
    assert ev.date_start == date(2027, 6, 4) and ev.date_end == date(2027, 6, 6) and ev.time_end == "23:00"
    ev2 = c.normalize({"@type": "Event", "name": "Placeholder end", "startDate": "2027-06-04T12:00", "endDate": "1970-01-01", "_page": {"venue": "AO", "url": "https://x.example/"}})
    assert ev2.date_end is None


def test_digest_format_sections_and_no_spam():
    base = {"generated_for": "2026-09-18", "summary": {"events_today": 0, "events_next_7_days": 0, "events_next_30_days": 0, "very_high": 0, "high": 0, "medium": 0,
            "new_events": 0, "changed_events": 0, "cancelled_events": 0, "sources_healthy": 3, "sources_total": 5, "open_actions": 0, "horizons": {}},
            "service_area": {"cities": ["London"], "top": []}, "top_opportunities": [], "by_category_7d": {}, "pipeline_status": "SUCCESS"}
    txt = format_daily_digest(base)
    assert "No high-priority taxi opportunities detected today." in txt and "🚕 UK TAXI INTELLIGENCE" in txt and "Pipeline:\nSUCCESS" in txt
    assert "🎓 EDUCATION" in txt and "🏟 SPORTS" in txt and "🎵 MUSIC" in txt and "🚨 EVENT CHANGES" in txt
    top = {"id": 1, "title": "Big Match", "date": "2026-09-19", "time": "17:30", "venue": "Emirates Stadium", "city": "London", "score": 89, "demand_level": "VERY_HIGH",
           "quality_level": "HIGH", "source_confidence": "TRUSTED", "top_action": "SEO", "post_window": {"start": "19:45", "end": "22:15"}, "capacity": 60704}
    base["summary"]["very_high"] = 1; base["service_area"]["top"] = [top]
    txt = format_daily_digest(base)
    assert "🔥 TOP 5" in txt and "Big Match" in txt and "Recommended action: SEO" in txt and "MODELLED" in txt and len(txt) <= 4000


def test_api_pagination_filters_and_alias(client):
    r = client.get("/api/events?page=1&page_size=2&sort=date").json()
    assert r["meta"]["page_size"] == 2 and len(r["data"]) <= 2
    assert client.get("/api/events?page_size=999").status_code == 422  # cap enforced at DB-level pagination
    for url in ["/api/events?missing=time,venue", "/api/events?status=CANCELLED", "/api/events?q=arsenal",
                "/api/marketing-actions?action_type=SEO&sort=score&q=taxi&page_size=5", "/api/actions?page_size=5", "/api/opportunities?page_size=5"]:
        b = client.get(url).json()
        assert b["success"] and "meta" in b, url


def test_db_unique_constraints(db_session):
    from app.db.models import Event, EventSource, Source
    src = db_session.scalar(select(Source).limit(1))
    e = Event(canonical_event_id="uq-test-1", fingerprint="fp1", title="T", normalized_title="t", date_start=date(2027, 1, 1))
    db_session.add(e); db_session.flush()
    db_session.add(EventSource(event_id=e.id, source_id=src.id, external_id="dup-1")); db_session.flush()
    db_session.add(EventSource(event_id=e.id, source_id=src.id, external_id="dup-1"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_pipeline_recovers_stale_running_run(db_session, monkeypatch):
    from app.collectors.base import CollectResult
    from app.db.models import PipelineRun
    from app.orchestration import pipeline as pl
    stale = PipelineRun(trigger="crash", status="RUNNING", started_at=datetime.utcnow() - timedelta(hours=5))
    db_session.add(stale); db_session.commit()

    class Zero:  # zero-result source must not fail the run nor delete events
        name = "curated"
        def run(self): return CollectResult("curated")
    monkeypatch.setattr(pl, "build_collectors", lambda only=None: [Zero()])
    before = db_session.scalar(select(__import__("sqlalchemy").func.count(pl.Event.id)))
    run = pl.run_pipeline(db_session, trigger="test", notify=False)
    db_session.refresh(stale)
    assert stale.status == "ABORTED" and run.status == "SUCCESS" and run.stages.get("recovered_stale_runs") == 1
    assert db_session.scalar(select(__import__("sqlalchemy").func.count(pl.Event.id))) == before


def test_service_area_from_settings_overrides_env(db_session):
    from app.core.service_area import load_service_area
    from app.db.models import Setting
    db_session.merge(Setting(key="service_area", value={"primary_city": "Oxford", "priority_cities": ["Oxford", "Reading"], "radius_miles": 10, "airports": ["LHR"]}))
    db_session.commit()
    sa = load_service_area(db_session)
    assert sa["source"] == "settings" and sa["cities"][0] == "Oxford" and "reading" in sa["normalized"] and sa["airports"] == ["LHR"]
    db_session.delete(db_session.get(Setting, "service_area")); db_session.commit()
    load_service_area(db_session)
