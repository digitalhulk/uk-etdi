"""Maps source keys in config/sources.yaml to collector classes."""
from __future__ import annotations

from app.core.config import sources_config

from .base import Collector
from .council import CouncilCollector, TourismCollector
from .curated import CuratedCollector
from .eventbrite import EventbriteCollector
from .feeds import ICalFeedCollector, RSSFeedCollector
from .institutions import CollegeCollector, SchoolCollector, UniversityCollector
from .jambase import JamBaseCollector
from .official import FootballFixturesCollector
from .ticketmaster import TicketmasterCollector
from .venue import VenuePageCollector

COLLECTORS: dict[str, type[Collector]] = {
    "ticketmaster": TicketmasterCollector,
    "eventbrite": EventbriteCollector,
    "jambase": JamBaseCollector,
    "football_fixtures": FootballFixturesCollector,
    "venue_pages": VenuePageCollector,
    "ical_feeds": ICalFeedCollector,
    "rss_feeds": RSSFeedCollector,
    "universities": UniversityCollector,
    "colleges": CollegeCollector,
    "schools": SchoolCollector,
    "councils": CouncilCollector,
    "tourism": TourismCollector,
    "curated": CuratedCollector,
}

# Category → source keys that can serve it (used by `cli collect --category`)
CATEGORY_SOURCES = {
    "sports": ["football_fixtures", "venue_pages", "ticketmaster"],
    "concerts": ["venue_pages", "ticketmaster", "jambase"],
    "music": ["venue_pages", "ticketmaster", "jambase"],
    "education": ["universities", "colleges", "schools", "curated"],
    "festivals": ["councils", "tourism", "ticketmaster"],
    "community": ["councils", "tourism"],
}


def build_collectors(only: list[str] | None = None, filters: dict | None = None) -> list[Collector]:
    out: list[Collector] = []
    for key, cfg in sorted(sources_config().items(), key=lambda kv: -kv[1].get("priority", 0)):
        if only and key not in only:
            continue
        cls = COLLECTORS.get(key)
        if not cls:
            continue
        inst = cls(cfg)
        inst.name = key
        inst.filters = filters or {}
        out.append(inst)
    return out
