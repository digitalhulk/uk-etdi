"""Phase 3 tests: providers, collectors' parsers, validation, sessions, bookings, exports, action transitions, security, CLI."""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from datetime import date, datetime, timedelta

import pytest

from app.schemas.normalized import NormalizedEvent


def _ev(**kw) -> NormalizedEvent:
    base = dict(source_key="t", external_id="x1", title="Test Concert", date_start=date.today() + timedelta(days=5), venue_name="Venue", city_name="Leeds")
    base.update(kw)
    return NormalizedEvent(**base)


# ---- providers (§6) -------------------------------------------------------------------------------------------------
def test_provider_registry_reports_all_kinds():
    from app.providers.registry import providers_status
    st = providers_status()
    for k in ("map", "notifications", "storage", "llm", "external_data"):
        assert k in st, k


def test_map_provider_free_default(monkeypatch):
    from app.providers.registry import get_map_provider
    p = get_map_provider()
    assert p.key in ("osm", "offline")
    assert "attribution" in p.tile_config()  # OSM requires attribution


def test_notification_providers_without_secrets_are_not_telegram():
    from app.providers.registry import get_notification_providers
    configured = [p.key for p in get_notification_providers() if p.is_configured()]
    assert "telegram" not in configured  # TELEGRAM_BOT_TOKEN is blank in tests


def test_llm_provider_disabled_by_default():
    from app.providers.registry import get_llm_provider
    p = get_llm_provider()
    assert p.is_configured() is False and p.complete('hello') is None


# ---- collectors: parsers with fixed payloads (§9–10) ------------------------------------------------------------------
def test_football_fixture_normalize_bst_split():
    from app.collectors.official import FootballFixturesCollector
    c = FootballFixturesCollector.__new__(FootballFixturesCollector)
    m = {"MatchNumber": 1, "RoundNumber": 1, "DateUtc": "2026-07-04 14:00:00Z", "Location": "Anfield", "HomeTeam": "Liverpool", "AwayTeam": "Everton",
         "_feed": {"competition": "Premier League", "slug": "epl-2026", "confidence": "TRUSTED"}}
    ev = c.normalize(m)
    assert ev is not None and ev.title == "Liverpool v Everton"
    assert ev.date_start == date(2026, 7, 4) and ev.time_start == "15:00"  # BST


def test_football_fixture_tba_rejected():
    from app.collectors.official import FootballFixturesCollector
    c = FootballFixturesCollector.__new__(FootballFixturesCollector)
    assert c.normalize({"DateUtc": "2026-07-04 14:00:00Z", "HomeTeam": "To Be Announced", "AwayTeam": "X", "_feed": {}}) is None


def test_ics_parser_extracts_vevents():
    from app.collectors.feeds import ICalFeedCollector
    c = ICalFeedCollector.__new__(ICalFeedCollector)
    text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:abc@x\nDTSTART:20261020T170000Z\nDTEND:20261020T180000Z\nSUMMARY:Public Lecture\n"
            "LOCATION:Lecture Theatre 1\nURL:https://example.org/e/1\nEND:VEVENT\nEND:VCALENDAR\n")
    items = list(c.parse(text))
    assert len(items) == 1 and "Public Lecture" in json.dumps(items[0], default=str)


def test_rss_parser_spektrix_dated_title():
    from app.collectors.feeds import RSSFeedCollector
    c = RSSFeedCollector.__new__(RSSFeedCollector)
    text = ("<?xml version='1.0'?><rss><channel><item><title>Macbeth | 12 November 2026 (7:30PM)</title>"
            "<link>https://example.org/macbeth</link><guid>g1</guid></item></channel></rss>")
    items = list(c.parse(text))
    assert len(items) == 1 and "Macbeth" in json.dumps(items[0])


def test_jsonld_parse_strict_false_and_offer_url():
    from app.collectors.venue import VenuePageCollector
    c = VenuePageCollector.__new__(VenuePageCollector)
    c.page_hint = None
    html = ('<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"MusicEvent","name":"Big\tGig",'
            '"startDate":"2026-11-01T19:30:00+00:00","location":{"@type":"Place","name":"Arena","address":{"addressLocality":"Leeds"}},'
            '"offers":{"url":"https://tickets.example.org/1"}}</script></html>')
    items = list(c.parse(html))
    assert len(items) == 1 and items[0].get("name", "").startswith("Big")


# ---- validation / classification (§7, §22) --------------------------------------------------------------------------
def test_non_event_title_rejected():
    from app.processors.validation import validate
    ok, reasons = validate(_ev(title="Pre-Order Refundable Booking Protection"))
    assert not ok and "non_event_title" in reasons


def test_validation_horizons_and_location():
    from app.processors.validation import validate
    assert "event_in_past" in validate(_ev(date_start=date.today() - timedelta(days=10)))[1]
    assert "event_too_far_future" in validate(_ev(date_start=date.today() + timedelta(days=500)))[1]
    assert "no_location" in validate(_ev(venue_name=None, city_name=None))[1]
    assert validate(_ev())[0]


def test_classify_title_beats_fallback_venue_hint():
    from app.processors.classify import classify
    cat, _, _ = classify("Liverpool v Everton", hint="fallback:concert")
    assert cat in ("football", "sports")
    cat2, _, _ = classify("Some Untitled Thing", hint="fallback:concert")
    assert cat2 in ("concert", "music")


def test_classify_configurable_categories_cover_named_types():
    from app.processors.classify import classify
    for title, want in [("Cheltenham Festival Day 1", ("horse_racing", "sports")), ("Stand-up: Live Comedy Night", ("standup", "comedy")),
                        ("Graduation Ceremony 2026", ("graduation", "education")), ("Hamilton the Musical", ("theatre", "musical"))]:
        cat, sub, _ = classify(title)
        assert cat in want or sub in want, (title, cat, sub)


# ---- session split logic (§22/§25 idempotency root cause) ------------------------------------------------------------
def test_different_session_thresholds():
    from app.orchestration.pipeline import _different_session
    assert _different_session("10:30", "12:00", min_gap_minutes=1)
    assert not _different_session("10:30", "12:00")          # default 120 min → same event, different-source discrepancy
    assert _different_session("11:00", "14:00")
    assert not _different_session(None, "14:00")
    assert not _different_session("14:00", "14:00")


def test_change_detection_url_only_upgrades_to_more_specific():
    from app.db.models import Event
    from app.processors.change_detection import detect_changes
    e = Event(title="A", date_start=date.today() + timedelta(days=3), official_url="https://x.org/events/a-show", status="SCHEDULED", time_start="19:00")
    inc = _ev(title="A", date_start=e.date_start, official_url="https://x.org/events/", time_start="19:00")
    fields = {c["field"] for c in detect_changes(e, inc, title="A")}
    assert "official_url" not in fields


def test_change_detection_time_change_emits_type():
    from app.db.models import Event
    from app.processors.change_detection import detect_changes
    e = Event(title="A", date_start=date.today() + timedelta(days=3), status="SCHEDULED", time_start="19:00")
    ch = detect_changes(e, _ev(title="A", date_start=e.date_start, time_start="20:00"), title="A")
    assert any(c["change_type"] == "TIME_CHANGED" for c in ch)


# ---- bookings (§31–33) ----------------------------------------------------------------------------------------------
def test_booking_to_canonical_and_rejects_missing_keys():
    from app.bookings.ingest import to_canonical
    rec = to_canonical({"booking_id": "B1", "pickup_datetime": "2026-09-10T18:30:00", "pickup_postcode": "ls11 0es", "fare": "12.50"})
    assert rec and rec["pickup_postcode"] == "LS11 0ES" and rec["fare"] == 12.5
    assert to_canonical({"pickup_datetime": "2026-09-10T18:30:00"}) is None


def test_booking_ingest_idempotent(db_session, tmp_path):
    from app.bookings.ingest import ingest, read_path
    p = tmp_path / "b.csv"
    p.write_text("booking_id,pickup_datetime,pickup_lat,pickup_lon\nT1,2026-09-10 18:30,53.79,-1.55\nT2,2026-09-10 19:00,53.80,-1.54\n,2026-09-10 19:00,1,1\n")
    s1 = ingest(db_session, read_path(p), "b.csv")
    s2 = ingest(db_session, read_path(p), "b.csv")
    assert s1["created"] == 2 and s1["rejected"] == 1
    assert s2["created"] == 0 and s2["updated"] == 2


def test_match_confidence_monotonic():
    from app.bookings.correlate import haversine_km, match_confidence
    assert abs(haversine_km(53.79, -1.55, 53.79, -1.55)) < 1e-6
    near = match_confidence(0.2, 10, 2.0, 180)
    far = match_confidence(1.9, 170, 2.0, 180)
    assert 0 <= far < near <= 1


def test_bookings_status_endpoint_deterministic_mode(client):
    r = client.get("/api/bookings/status")
    assert r.status_code == 200
    body = r.json()
    assert body.get("mode") == "DETERMINISTIC" or body.get("model_mode") == "DETERMINISTIC" or "DETERMINISTIC" in json.dumps(body)


# ---- exports (§59) --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/api/export/events", "/api/export/opportunities", "/api/export/actions", "/api/export/reports"])
def test_export_csv_and_json(client, path):
    r = client.get(path, params={"format": "csv"})
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    list(csv.reader(io.StringIO(r.text)))  # parses
    r2 = client.get(path, params={"format": "json"})
    assert r2.status_code == 200 and isinstance(r2.json(), list)


def test_export_rejects_unknown_format(client):
    assert client.get("/api/export/events", params={"format": "xml"}).status_code in (400, 422)


# ---- API surface (§52) ----------------------------------------------------------------------------------------------
def test_new_api_routes_exist(client):
    assert client.get("/api/health/detailed").status_code == 200
    assert client.get("/api/marketing-actions/999999").status_code == 404
    assert client.get("/api/dashboard/summary").status_code == 200
    body = client.get("/api/dashboard/summary").json()
    assert "next_scheduled_run" in json.dumps(body) and "data_freshness" in json.dumps(body)


def test_disabled_api_sources_show_reason(client):
    src = client.get("/api/sources").json()
    items = src.get("data", src) if isinstance(src, dict) else src
    by_key = {s["key"]: s for s in items}
    for k in ("ticketmaster", "eventbrite", "jambase"):
        if k in by_key:
            assert by_key[k]["status"] == "DISABLED" and "API key not configured" in (by_key[k].get("disabled_reason") or "")


def test_settings_do_not_leak_secrets(client, monkeypatch):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()["data"]
    # integrations are booleans (configured or not), never the secret values
    assert all(isinstance(v, bool) for v in body["integrations"].values())
    for k in ("telegram_bot_token", "telegram_chat_id", "google_sheets_webhook", "api_admin_token", "smtp_password"):
        assert k not in json.dumps(body)


# ---- marketing action transitions (§36) ------------------------------------------------------------------------------
def test_action_transitions(client, db_session):
    from app.db.models import MarketingAction, Event
    ev = db_session.query(Event).first()
    if ev is None:
        pytest.skip("no events in test DB")
    a = MarketingAction(event_id=ev.id, action_type="SEO", title="t", status="NEW", priority="HIGH")
    db_session.add(a); db_session.commit()
    aid = a.id
    assert client.post(f"/api/marketing-actions/actions/{aid}/plan").json()["status"] == "PLANNED"
    assert client.post(f"/api/marketing-actions/actions/{aid}/schedule").json()["status"] == "SCHEDULED"
    assert client.post(f"/api/marketing-actions/actions/{aid}/start").json()["status"] == "IN_PROGRESS"
    assert client.post(f"/api/marketing-actions/actions/{aid}/done").json()["status"] == "DONE"
    assert client.post(f"/api/marketing-actions/actions/{aid}/reopen").json()["status"] == "NEW"
    assert client.post(f"/api/marketing-actions/actions/{aid}/dismiss").json()["status"] == "DISMISSED"
    assert client.get(f"/api/marketing-actions/{aid}").json()["status"] == "DISMISSED"


# ---- security (§60–61) ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://169.254.169.254/latest", "file:///etc/passwd", "http://localhost:8000/", "ftp://example.org/"])
def test_ssrf_blocked(url):
    from app.core.netsafe import UnsafeURL, validate_url
    with pytest.raises(UnsafeURL):
        validate_url(url, resolve=False)


def test_admin_endpoints_require_token(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.get_settings(), "api_admin_token", "secret")
    assert client.post("/api/pipeline/run").status_code == 401
    assert client.post("/api/pipeline/run", headers={"X-Admin-Token": "secret"}).status_code in (200, 202, 409)


# ---- CLI (§54) ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("args", [["health"], ["coverage"], ["events", "--days", "1", "--json"], ["bookings", "status"], ["sources"]])
def test_cli_commands_exit_zero(args):
    r = subprocess.run([sys.executable, "-m", "app.cli", *args], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]


def test_source_detail_and_calendar_alias(client):
    srcs = client.get("/api/sources").json()["data"]
    r = client.get(f"/api/sources/{srcs[0]['id']}")
    assert r.status_code == 200 and "recent_runs" in r.json()["data"]
    assert client.get("/api/sources/999999").status_code == 404
    d = date.today()
    assert client.get("/api/calendar", params={"start": d.isoformat(), "end": (d + timedelta(days=7)).isoformat()}).status_code == 200


def test_put_settings_rejects_secrets(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.get_settings(), "api_admin_token", "secret")
    h = {"X-Admin-Token": "secret"}
    assert client.put("/api/settings", json={"telegram_bot_token": "x"}, headers=h).status_code == 400
    r = client.put("/api/settings", json={"home_city": "leeds"}, headers=h)
    assert r.status_code == 200 and r.json()["data"]["home_city"] == "leeds"
    assert client.put("/api/settings", json={"home_city": "leeds"}).status_code == 401


def test_source_regression_flagged(db_session, monkeypatch):
    """§64: a previously productive source returning far fewer events is flagged, never treated as a clean success."""
    from app.db.models import ErrorLog, PipelineRun, Source, SourceRun
    from app.orchestration.pipeline import Pipeline
    from app.collectors.base import CollectResult
    src = db_session.query(Source).filter_by(key="curated").first()
    run0 = PipelineRun(trigger="test"); db_session.add(run0); db_session.flush()
    db_session.add(SourceRun(source_id=src.id, pipeline_run_id=run0.id, status="HEALTHY", events_collected=40)); db_session.commit()

    class Fake:
        name = "curated"
        def run(self):
            return CollectResult("curated", status="HEALTHY", events=[])
    p = Pipeline(db_session, trigger="test", notify=False, only_sources=["curated"])
    db_session.add(p.run); db_session.flush()
    import app.orchestration.pipeline as pl
    monkeypatch.setattr(pl, "build_collectors", lambda only: [Fake()])
    p._collect()
    assert p.regressions and p.regressions[0]["source"] == "curated"
    assert db_session.query(ErrorLog).filter(ErrorLog.message.like("regression:%")).count() >= 1
