from datetime import date

from app.core.config import scoring_config
from app.db.models import City, Venue
from app.intelligence.demand_score import compute_windows, score_event


def _venue(cap=60000, station=2.5, airport=13):
    return Venue(name="Big", normalized_name="big", capacity=cap, capacity_source="test", venue_type="stadium", importance_score=1.0,
                 station_distance_km=station, airport_distance_km=airport, is_seeded=True)


def _city(priority=100, tourism=1.0):
    return City(name="London", normalized_name="london", priority=priority, tourism=tourism)


def test_weights_sum_to_100():
    assert sum(scoring_config()["weights"].values()) == 100


def test_score_is_explained_and_bounded():
    r = score_event(category="music", date_start=date(2026, 10, 3), date_end=None, time_start="19:30", time_end=None, venue=_venue(), city=_city())
    assert 0 <= r.score <= 100
    assert r.reasons and any("Major venue" in x for x in r.reasons)
    assert any("Weekend" in x for x in r.reasons)
    assert set(r.components) == set(scoring_config()["weights"])
    assert r.demand_level == "VERY_HIGH"


def test_small_venue_scores_lower_and_cancelled_zero():
    big = score_event(category="sports", date_start=date(2026, 10, 3), date_end=None, time_start="15:00", time_end=None, venue=_venue(), city=_city())
    small = score_event(category="sports", date_start=date(2026, 10, 3), date_end=None, time_start="15:00", time_end=None, venue=_venue(cap=800), city=_city(priority=40, tourism=0.1))
    assert big.score > small.score + 20
    cancelled = score_event(category="sports", date_start=date(2026, 10, 3), date_end=None, time_start="15:00", time_end=None, venue=_venue(), city=_city(), status="CANCELLED")
    assert cancelled.score == 0


def test_windows_are_labelled_modelled():
    w = compute_windows("music", date(2026, 10, 3), "19:00", "22:00")
    assert w["label"] == "Modelled demand window"
    assert w["pre_event_window"] == {"start": "16:00", "end": "19:00", "type": "arrivals"}
    assert w["post_event_window"]["start"] == "22:00" and w["post_event_window"]["end"] == "00:30"
    assert compute_windows("music", date(2026, 10, 3), None, None)["available"] is False
