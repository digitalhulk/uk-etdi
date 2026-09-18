"""Phase 2: SSRF policy, JSON-LD extraction, quality/status engine, gating, coverage endpoints, CLI."""
from datetime import date, datetime, timedelta

import pytest

from app.collectors.base import CollectResult, Collector
from app.core.netsafe import UnsafeURL, validate_url
from app.intelligence.quality import derive_status, freshness_score, is_source_silent, quality_for
from app.schemas.normalized import NormalizedEvent


# ---- SSRF ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost:8000/", "http://169.254.169.254/latest", "file:///etc/passwd",
                                 "ftp://example.com/", "http://10.0.0.5/", "http://[::1]/"])
def test_validate_url_rejects_private_and_bad_schemes(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, resolve=False)


def test_validate_url_allowlist():
    assert validate_url("https://www.thejockeyclub.co.uk/x", ("thejockeyclub.co.uk",), resolve=False)
    with pytest.raises(UnsafeURL):
        validate_url("https://evil.example/x", ("thejockeyclub.co.uk",), resolve=False)


# ---- JSON-LD ---------------------------------------------------------------------------------------------
HTML = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"MusicEvent","name":"Test Gig",
"startDate":"2027-03-01T19:30","location":{"@type":"Place","name":"AO Arena","address":{"addressLocality":"Manchester","postalCode":"M3 1AR"}},
"offers":{"url":"https://tickets.example/x","availability":"https://schema.org/SoldOut"},"url":"https://venue.example/e/1"}</script>
<script type="application/ld+json">[{"@type":"Event","name":"Bad\tControl","startDate":"2027-03-02"},{"@type":"Organization","name":"nope"}]</script>
</head><body><a href="/events/detail/one/">1</a><a href="/events/detail/two/">2</a><a href="/news/x">n</a></body></html>"""


def test_extract_jsonld_and_detail_links():
    c = Collector({})
    items = list(c.extract_jsonld_events(HTML))
    assert [i["name"] for i in items] == ["Test Gig", "Bad\tControl"]  # strict=False tolerates control chars; Organization dropped
    links = c.detail_links(HTML, "https://www.ao-arena.com/events", "/events/detail/")
    assert links == ["https://www.ao-arena.com/events/detail/one/", "https://www.ao-arena.com/events/detail/two/"]


def test_venue_normalize_sold_out_and_tz():
    from app.collectors.venue import VenuePageCollector
    c = VenuePageCollector({})
    it = list(c.extract_jsonld_events(HTML))[0]
    it["_page"] = {"venue": "AO Arena", "city": "Manchester", "url": "https://www.ao-arena.com/events", "category_hint": "concerts"}
    ev = c.normalize(it)
    assert ev.date_start == date(2027, 3, 1) and ev.time_start == "19:30" and ev.sold_out and ev.status == "SOLD_OUT"
    assert ev.postcode == "M3 1AR" and ev.ticket_url.startswith("https://tickets") and ev.event_subtype == "MusicEvent"


# ---- quality / freshness / status ----------------------------------------------------------------------
def test_quality_levels_and_reasons():
    hi = quality_for(source_confidence="OFFICIAL", time_start="19:00", venue_matched=True, venue_named=True, has_city=True, official_url="https://x",
                     has_geo=True, category="music", source_count=2, freshness=100)
    lo = quality_for(source_confidence="UNVERIFIED", time_start=None, venue_matched=False, venue_named=False, has_city=False, official_url=None,
                     has_geo=False, category="other", source_count=1, freshness=10)
    assert hi.level == "HIGH" and hi.score >= 90 and any("OFFICIAL" in r for r in hi.reasons)
    assert lo.level == "LOW" and "stale_penalty" in lo.components
    school = quality_for(source_confidence="OFFICIAL", time_start="09:00", venue_matched=False, venue_named=True, has_city=True, official_url=None,
                         has_geo=False, category="education", source_count=1, freshness=100, is_school=True, school_confidence="LOW")
    assert school.components["school_event_penalty"] < 0


def test_freshness_and_silence():
    now = datetime(2026, 9, 18, 12)
    assert freshness_score(now, now) == 100
    assert freshness_score(now - timedelta(days=7), now) == 55
    assert freshness_score(now - timedelta(days=60), now) == 10
    assert not is_source_silent(now - timedelta(days=2), date(2026, 10, 1), now)
    assert is_source_silent(now - timedelta(days=30), date(2026, 10, 1), now)
    assert not is_source_silent(now - timedelta(days=30), date(2026, 9, 1), now)  # past event never "silent"


def test_status_engine_rules():
    kw = dict(incoming_confidence="OFFICIAL", sold_out=False, source_count=1, date_start=date(2027, 1, 1), date_changed=False, today=date(2026, 9, 18))
    assert derive_status(current_status="SCHEDULED", incoming_status="SCHEDULED", title="Show (CANCELLED)", **kw)[0] == "CANCELLED"
    assert derive_status(current_status="SCHEDULED", incoming_status="POSTPONED", title="Show", **kw)[0] == "POSTPONED"
    assert derive_status(current_status="SCHEDULED", incoming_status="SCHEDULED", title="Show", **{**kw, "date_changed": True})[0] == "RESCHEDULED"
    assert derive_status(current_status="SCHEDULED", incoming_status="SCHEDULED", title="Show", **{**kw, "sold_out": True})[0] == "SOLD_OUT"
    assert derive_status(current_status="SCHEDULED", incoming_status="SCHEDULED", title="Show", **{**kw, "source_count": 2})[0] == "CONFIRMED"
    assert derive_status(current_status="CONFIRMED", incoming_status="SCHEDULED", title="Show", **kw)[0] == "CONFIRMED"  # never downgrade
    assert derive_status(current_status="CANCELLED", incoming_status="SCHEDULED", title="Show", **kw)[0] == "CANCELLED"  # plain listing doesn't reverse
    assert derive_status(current_status="SCHEDULED", incoming_status="SCHEDULED", title="Show", **{**kw, "date_start": date(2026, 1, 1)})[0] == "COMPLETED"


# ---- collector status semantics -------------------------------------------------------------------------
class _Empty(Collector):
    name = "x"
    def collect(self, config=None):
        return CollectResult("x")


class _AllBlocked(Collector):
    name = "y"
    def collect(self, config=None):
        r = CollectResult("y"); r.endpoints_attempted = 2; r.blocked = ["a", "b"]; r.warnings = ["a: 403", "b: 403"]
        return r


def test_run_status_empty_vs_failed():
    assert _Empty({}).run().status == "EMPTY"
    r = _AllBlocked({}).run()
    assert r.status == "BLOCKED" and "403" in r.error  # all endpoints 403 → BLOCKED, never retried


# ---- API -------------------------------------------------------------------------------------------------
def test_coverage_and_quality_endpoints(client):
    r = client.get("/api/coverage").json()
    assert r["success"] and 0 <= r["data"]["configured_coverage_index"] <= 100
    assert "not a measure of all UK events" in r["data"]["disclaimer"]
    assert {"today", "7d", "30d", "90d"} <= set(r["data"]["events"]["horizons"])
    q = client.get("/api/data-quality").json()["data"]
    assert "missing" in q and "quality_levels" in q
    ev = client.get("/api/events?quality=HIGH,MEDIUM&confidence=OFFICIAL,TRUSTED,CURATED&page_size=5").json()
    assert ev["success"] and ev["meta"]["page_size"] == 5


def test_event_detail_has_facts_modelled_recommendation_split(client, db_session):
    from sqlalchemy import select
    from app.db.models import Event
    e = db_session.scalar(select(Event).limit(1))
    if e is None:
        pytest.skip("no events in test DB")
    d = client.get(f"/api/events/{e.id}").json()["data"]
    assert {"facts", "modelled", "recommendations"} <= set(d)
    assert d["modelled"]["label"] == "MODELLED" and d["recommendations"]["label"] == "RECOMMENDATION"
    assert "sources" in d["facts"] and "score_breakdown" in d["modelled"]
    snaps = client.get(f"/api/events/{e.id}/snapshots").json()
    assert snaps["success"]


def test_cli_sources_and_health(capsys):
    from app.cli import main
    assert main(["sources"]) == 0
    out = capsys.readouterr().out
    assert "venue_pages" in out and "universities" in out
    assert main(["health"]) == 0


def test_action_gating_blocks_low_quality():
    from types import SimpleNamespace
    from app.intelligence.marketing import gate
    ev = SimpleNamespace(status="SCHEDULED", opportunity_score=90, quality_level="LOW", event_quality_score=30, date_start=date.today() + timedelta(days=3),
                         city=None, city_name_raw="London", venue=None)
    ok, reasons = gate(ev)
    assert not ok and "quality" in reasons[0]
    ev.quality_level = "HIGH"
    ok, reasons = gate(ev)
    assert ok and any("inside service area" in r for r in reasons)
