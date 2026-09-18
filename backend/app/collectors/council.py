"""Councils + tourism boards from config/councils.yaml (fields: council, region, city, events_url, calendar_url, rss_url, ical_url, enabled, kind).
Fallback chain: ical_url → rss_url → calendar_url/events_url JSON-LD (listing → optional detail pages)."""
from __future__ import annotations

from typing import Any

from app.core.config import load_config

from .base import CollectResult, Collector
from .feeds import ICalFeedCollector, RSSFeedCollector
from .venue import VenuePageCollector


def councils_config() -> list[dict[str, Any]]:
    return load_config("councils.yaml").get("councils", [])


class CouncilCollector(Collector):
    name = "councils"
    source_confidence = "OFFICIAL"
    kinds: tuple[str, ...] = ("council",)

    def _targets(self) -> list[dict[str, Any]]:
        out = [c for c in councils_config() if c.get("enabled", True) and c.get("kind", "council") in self.kinds]
        city = (self.filters or {}).get("city")
        if city:
            out = [c for c in out if (c.get("city") or "").lower() == city.lower()]
        return out

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        result = CollectResult(self.name)
        for c in self._targets():
            before = len(result.events)
            common = {"name": c["council"], "city": c.get("city"), "category_hint": c.get("category_hint") or "fallback:community", "organizer": c["council"]}
            for kind, url in (("ical", c.get("ical_url")), ("rss", c.get("rss_url"))):
                if not url or len(result.events) > before:
                    continue
                sub = (ICalFeedCollector if kind == "ical" else RSSFeedCollector)({"feeds": [{**common, "url": url}]})
                sub.name = self.name
                self._merge(result, sub.collect())
            page = c.get("calendar_url") or c.get("events_url")
            if (page or c.get("wp_json_url")) and len(result.events) == before:
                sub = VenuePageCollector({"registry": False, "pages": [{"url": page, "venue": None, "city": c.get("city"), "category_hint": common["category_hint"],
                                                     "detail_pattern": c.get("detail_pattern") or r"/(?:whats-on|events?|event)/[a-z0-9][a-z0-9/-]+/?$", "max_detail_pages": int(c.get("max_detail_pages", 0)),
                                                     "page_pattern": c.get("page_pattern"), "max_listing_pages": int(c.get("max_listing_pages", 1)), "json_url": c.get("json_url"),
                                                     "wp_json_url": c.get("wp_json_url"), "max_wp_items": int(c.get("max_wp_items", 60))}]})
                sub.name = self.name
                self._merge(result, sub.collect())
            for ev in result.events[before:]:
                ev.organizer = ev.organizer or c["council"]
                ev.city_name = ev.city_name or c.get("city")
        return result

    @staticmethod
    def _merge(result: CollectResult, r: CollectResult) -> None:
        result.events.extend(r.events); result.raw_payloads.extend(r.raw_payloads); result.warnings.extend(r.warnings)
        result.blocked.extend(r.blocked); result.endpoints_attempted += r.endpoints_attempted; result.endpoints_ok += r.endpoints_ok


class TourismCollector(CouncilCollector):
    name = "tourism"
    kinds = ("tourism",)
    source_confidence = "TRUSTED"  # DMOs aggregate third-party listings
