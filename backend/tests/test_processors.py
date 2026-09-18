from datetime import date, datetime, timezone

from app.processors.classify import classify
from app.processors.deduplicate import fingerprint, similarity, AUTO_MERGE_THRESHOLD
from app.processors.normalize import normalize_postcode, normalize_status, normalize_title, parse_time, parse_uk_date, split_local


def test_uk_date_formats():
    assert parse_uk_date("21/09/2026") == date(2026, 9, 21)
    assert parse_uk_date("2026-09-21") == date(2026, 9, 21)
    assert parse_uk_date("Sat 21 Sep 2026") == date(2026, 9, 21)
    assert parse_uk_date("21.09.26") == date(2026, 9, 21)
    assert parse_uk_date("not a date") is None


def test_time_parsing_handles_unknown():
    assert parse_time("19:30") == "19:30"
    assert parse_time("7.30pm") == "19:30"
    assert parse_time("TBC") is None
    assert parse_time(None) is None


def test_bst_gmt_conversion():
    # 15 Aug 19:00 UTC -> 20:00 BST ; 15 Dec 15:00 UTC -> 15:00 GMT
    assert split_local(datetime(2026, 8, 15, 19, 0, tzinfo=timezone.utc)) == (date(2026, 8, 15), "20:00")
    assert split_local(datetime(2026, 12, 15, 15, 0, tzinfo=timezone.utc)) == (date(2026, 12, 15), "15:00")
    # BST midnight crossover
    assert split_local(datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc)) == (date(2026, 7, 2), "00:30")


def test_postcode_and_status():
    assert normalize_postcode("ha90ws") == "HA9 0WS"
    assert normalize_status("https://schema.org/EventCancelled") == "CANCELLED"
    assert normalize_status("onsale") == "SCHEDULED"
    assert normalize_status("postponed") == "POSTPONED"


def test_classifier_keywords_from_config():
    assert classify("Coldplay Live at Wembley")[:2] == ("music", "concert")
    assert classify("Arsenal v Chelsea", "football Premier League")[:2] == ("sports", "football")
    assert classify("Freshers Week 2026")[:2] == ("education", "university")
    assert classify("Manchester Food Festival")[:2] == ("festival", "food")
    assert classify("Random thing")[0] == "other"


def test_fingerprint_stable_and_title_normalized():
    a = fingerprint("The Killers - Live!", date(2026, 10, 1), "The O2", "London")
    b = fingerprint("Killers Live", date(2026, 10, 1), "the o2", "LONDON")
    assert a == b
    assert normalize_title("The Killers - Live!") == "killers"


def test_fuzzy_similarity_thresholds():
    conf, _ = similarity("Liverpool v Bournemouth", "Liverpool vs AFC Bournemouth", "Anfield", "Anfield", "Liverpool", "Liverpool", True)
    assert conf >= AUTO_MERGE_THRESHOLD
    conf2, _ = similarity("Liverpool v Bournemouth", "Everton v Arsenal", "Anfield", "Goodison Park", "Liverpool", "Liverpool", True)
    assert conf2 < 0.7
    assert similarity("A", "A", None, None, None, None, False)[0] == 0.0
