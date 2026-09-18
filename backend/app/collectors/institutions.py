"""Universities / colleges / schools from config/institutions.yaml.

Per institution fallback chain: ical_url → rss_url → events_url (JSON-LD listing → detail pages).
Only public event calendars. Events get an education hint; school events carry `school_event_confidence`
(quality gate applied later in the quality engine)."""
from __future__ import annotations

from typing import Any

from app.core.config import load_config

from .base import CollectResult, Collector
from .feeds import ICalFeedCollector, RSSFeedCollector
from .venue import VenuePageCollector

TYPE_HINTS = {"university": "university", "college": "college education", "sixth_form": "college education", "school": "school"}


def institutions_config() -> list[dict[str, Any]]:
    return load_config("institutions.yaml").get("institutions", [])


class InstitutionCollector(Collector):
    name = "institutions"
    source_confidence = "OFFICIAL"
    institution_types: tuple[str, ...] = ("university", "college", "sixth_form", "school")

    def _targets(self) -> list[dict[str, Any]]:
        out = [i for i in institutions_config() if i.get("enabled", True) and i.get("type") in self.institution_types]
        city = (self.filters or {}).get("city")
        if city:
            out = [i for i in out if (i.get("city") or "").lower() == city.lower()]
        return out

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        result = CollectResult(self.name)
        for inst in self._targets():
            before = len(result.events)
            hint = f"{TYPE_HINTS.get(inst.get('type'), 'education')} {inst.get('category_hint') or ''}".strip()
            common = {"name": inst["name"], "venue": inst.get("venue") or inst["name"], "city": inst.get("city"), "category_hint": hint, "organizer": inst["name"]}
            for kind, url in (("ical", inst.get("ical_url")), ("rss", inst.get("rss_url"))):
                if not url or len(result.events) > before:
                    continue
                sub = (ICalFeedCollector if kind == "ical" else RSSFeedCollector)({"feeds": [{**common, "url": url, "pubdate_is_start": bool(inst.get("rss_pubdate_is_start")), "website": inst.get("website")}]})
                sub.name = self.name
                r = sub.collect()
                self._merge(result, r)
            if inst.get("events_url") and len(result.events) == before:
                sub = VenuePageCollector({"registry": False, "pages": [{"url": inst["events_url"], "venue": common["venue"], "city": inst.get("city"), "category_hint": hint,
                                                     "detail_pattern": inst.get("detail_pattern") or r"/events?/[a-z0-9][a-z0-9-]+/?$", "max_detail_pages": int(inst.get("max_detail_pages", 0)),
                                                     "page_pattern": inst.get("page_pattern"), "max_listing_pages": int(inst.get("max_listing_pages", 1)), "json_url": inst.get("json_url")}]})
                sub.name = self.name
                self._merge(result, sub.collect())
            for ev in result.events[before:]:
                ev.organizer = ev.organizer or inst["name"]
                ev.raw.setdefault("institution_type", inst.get("type"))
        return result

    @staticmethod
    def _merge(result: CollectResult, r: CollectResult) -> None:
        result.events.extend(r.events); result.raw_payloads.extend(r.raw_payloads); result.warnings.extend(r.warnings)
        result.blocked.extend(r.blocked); result.endpoints_attempted += r.endpoints_attempted; result.endpoints_ok += r.endpoints_ok


class UniversityCollector(InstitutionCollector):
    name = "universities"
    institution_types = ("university",)


class CollegeCollector(InstitutionCollector):
    name = "colleges"
    institution_types = ("college", "sixth_form")


class SchoolCollector(InstitutionCollector):
    name = "schools"
    institution_types = ("school",)
    source_confidence = "TRUSTED"
