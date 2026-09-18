"""Registry-driven venue collector (config/venues.yaml entries with `official_events_url`).

Fallback chain per venue (first that yields events wins, remaining steps skipped):
  1. public JSON endpoint      (venue.events_json_url)
  2. iCal / ICS                (venue.ical_url)
  3. RSS                       (venue.rss_url)
  4. JSON-LD on listing page   (venue.official_events_url)
  5. JSON-LD on detail pages   (links matching venue.detail_pattern, capped by max_detail_pages)
robots.txt is checked for every page; 401/403 mark the venue BLOCKED for this run (never retried aggressively).
Also honours the legacy `pages:` list in sources.yaml."""
from __future__ import annotations

import hashlib
import html as html_mod
from typing import Any, Iterable

from app.core.config import venues_config
from app.processors.normalize import normalize_status, parse_time, parse_uk_date, split_local
from app.schemas.normalized import NormalizedEvent

from .base import CollectResult, Collector
from .feeds import ICalFeedCollector, RSSFeedCollector

DEFAULT_DETAIL_PATTERN = r"/events?/(?:detail/)?[a-z0-9][a-z0-9-]+/?$"


def parse_schema_datetime(value: str | None) -> tuple[Any, str | None]:
    """schema.org startDate may be date, naive datetime, or tz-aware ISO. Returns (date, HH:MM|None) in Europe/London."""
    if not value:
        return None, None
    v = str(value).strip()
    if len(v) <= 10:
        return parse_uk_date(v), None
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return parse_uk_date(v[:10]), parse_time(v[11:16])
    if dt.tzinfo is not None:
        return split_local(dt)
    return dt.date(), dt.strftime("%H:%M")


def _merge_hint(schema_type: str, page_hint: str | None) -> str | None:
    """Schema.org subtype (MusicEvent…) is a strong hint; a bare 'Event' type carries no signal. A page hint prefixed
    'fallback:' must stay prefixed so the classifier only uses it when title/description match nothing."""
    strong = schema_type if schema_type and schema_type.lower() != "event" else ""
    hint = (page_hint or "").strip()
    if hint.lower().startswith("fallback:"):
        return f"{strong} {hint}".strip() if strong else hint
    return " ".join(filter(None, [strong, hint])).strip() or None


class VenuePageCollector(Collector):
    name = "venue_pages"
    source_confidence = "OFFICIAL"  # official venue website

    def _targets(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        targets = []
        for v in ([] if cfg.get("registry") is False else venues_config()):
            if v.get("enabled", True) and (v.get("official_events_url") or v.get("events_json_url") or v.get("ical_url") or v.get("rss_url") or v.get("wp_json_url")):
                targets.append({"venue": v["name"], "city": v.get("city"), "postcode": v.get("postcode"), "url": v.get("official_events_url"),
                                "json_url": v.get("events_json_url"), "ical_url": v.get("ical_url"), "rss_url": v.get("rss_url"),
                                "wp_json_url": v.get("wp_json_url"), "max_wp_items": int(v.get("max_wp_items", 60)),
                                "prefer_schema_venue": bool(v.get("prefer_schema_venue") or v.get("venue_type") == "theatre_group"),
                                "detail_pattern": v.get("detail_pattern") or DEFAULT_DETAIL_PATTERN, "max_detail_pages": int(v.get("max_detail_pages", 0)),
                                "page_pattern": v.get("page_pattern"), "max_listing_pages": int(v.get("max_listing_pages", 1)),
                                "category_hint": v.get("category_hint"), "website": v.get("official_website")})
        for p in cfg.get("pages", []) or []:  # legacy
            targets.append({**p, "detail_pattern": p.get("detail_pattern") or DEFAULT_DETAIL_PATTERN, "max_detail_pages": int(p.get("max_detail_pages", 0)),
                            "max_wp_items": int(p.get("max_wp_items", 60))})
        city = (self.filters or {}).get("city")
        if city:
            targets = [t for t in targets if (t.get("city") or "").lower() == city.lower()]
        return targets

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        cfg = {**self.config, **(config or {})}
        result = CollectResult(self.name)
        for t in self._targets(cfg):
            got = self._collect_venue(t, result)
            self.log.debug("venue %s → %s events", t["venue"], got)
        return result

    def _collect_venue(self, t: dict[str, Any], result: CollectResult) -> int:
        before = len(result.events)
        # 1. public JSON
        if t.get("json_url"):
            url, pages = t["json_url"], 0
            while url and pages < int(t.get("max_json_pages", 12)):
                pages += 1
                r = self.safe_fetch(url, result, f"{t['venue']} json")
                if r is None:
                    break
                try:
                    payload = r.json()
                except ValueError:
                    result.warnings.append(f"{t['venue']}: json endpoint returned non-JSON")
                    break
                items = payload if isinstance(payload, list) else payload.get("events") or payload.get("data") or []
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    it["_page"] = t
                    result.raw_payloads.append({k: v for k, v in it.items() if k not in ("_page", "description", "excerpt", "image")})
                    ev = self.normalize(it)
                    if ev:
                        result.events.append(ev)
                # WordPress "The Events Calendar" (tribe) style pagination
                url = payload.get("next_rest_url") if isinstance(payload, dict) else None
            if len(result.events) > before:
                return len(result.events) - before
        # 2. iCal
        if t.get("ical_url"):
            sub = ICalFeedCollector({"feeds": [{"name": t["venue"], "url": t["ical_url"], "venue": t["venue"], "city": t.get("city"), "category_hint": t.get("category_hint")}]})
            sub.name = self.name
            r = sub.collect()
            result.events.extend(r.events); result.raw_payloads.extend(r.raw_payloads); result.warnings.extend(r.warnings)
            result.endpoints_attempted += r.endpoints_attempted; result.endpoints_ok += r.endpoints_ok
            if len(result.events) > before:
                return len(result.events) - before
        # 3. RSS
        if t.get("rss_url"):
            sub = RSSFeedCollector({"feeds": [{"name": t["venue"], "url": t["rss_url"], "venue": t["venue"], "city": t.get("city"), "category_hint": t.get("category_hint")}]})
            sub.name = self.name
            r = sub.collect()
            result.events.extend(r.events); result.raw_payloads.extend(r.raw_payloads); result.warnings.extend(r.warnings)
            result.endpoints_attempted += r.endpoints_attempted; result.endpoints_ok += r.endpoints_ok
            if len(result.events) > before:
                return len(result.events) - before
        # 3b. WordPress REST index (public wp-json list of event posts) → JSON-LD on each event page.
        # Used where the listing page is JS-rendered but every event page carries schema.org Event data.
        if t.get("wp_json_url"):
            got = self._collect_wp_index(t, result)
            if got:
                return got
        # 4. JSON-LD listing
        if not t.get("url"):
            return 0
        r = self.safe_fetch(t["url"], result, f"{t['venue']} listing")
        if r is None:
            return 0
        html = r.text
        seen: set[str] = set()

        def _ingest(page_html: str, page_url: str) -> int:
            n = 0
            for it in self.parse(page_html):
                it["_page"] = {**t, "url": page_url}
                ev = self.normalize(it)
                if ev and ev.external_id not in seen:
                    seen.add(ev.external_id)
                    result.raw_payloads.append({k: v for k, v in it.items() if k != "_page"})
                    result.events.append(ev)
                    n += 1
            return n

        _ingest(html, t["url"])
        # 4b. paginated listings (e.g. WordPress /whats-on/list/page/N/) — stop at first page adding nothing new
        if t.get("page_pattern") and int(t.get("max_listing_pages") or 1) > 1:
            for n in range(2, int(t["max_listing_pages"]) + 1):
                purl = t["page_pattern"].format(n=n)
                rr = self.safe_fetch(purl, result, f"{t['venue']} page {n}")
                if rr is None or _ingest(rr.text, purl) == 0:
                    break
        # 5. detail pages (only for venues that opt in; listing JSON-LD is often truncated to first N)
        if t["max_detail_pages"] > 0:
            links = self.detail_links(html, t["url"], t["detail_pattern"])
            for link in links[: t["max_detail_pages"]]:
                rr = self.safe_fetch(link, result, f"{t['venue']} detail")
                if rr is None:
                    if link in result.blocked:
                        break  # stop hammering a blocked host
                    continue
                for it in self.parse(rr.text):
                    it["_page"] = {**t, "url": link}
                    ev = self.normalize(it)
                    if ev and ev.external_id not in seen:
                        seen.add(ev.external_id)
                        result.raw_payloads.append({k: v for k, v in it.items() if k != "_page"})
                        result.events.append(ev)
        return len(result.events) - before

    def parse(self, html: str) -> Iterable[dict[str, Any]]:
        return self.extract_jsonld_events(html)

    def _collect_wp_index(self, t: dict[str, Any], result: CollectResult) -> int:
        """Page through `wp_json_url` (WordPress REST collection, most recently modified first), then read the JSON-LD
        Event blocks from each post's public page. Stops at the first page whose posts are all already known."""
        before = len(result.events)
        seen: set[str] = set()
        base, per_page, fetched, page_no = t["wp_json_url"], 20, 0, 1
        limit = int(t.get("max_wp_items") or 60)
        while fetched < limit:
            sep = "&" if "?" in base else "?"
            r = self.safe_fetch(f"{base}{sep}per_page={per_page}&page={page_no}&orderby=modified&order=desc&_fields=id,link,modified", result, f"{t['venue']} wp-json p{page_no}")
            if r is None:
                break
            try:
                posts = r.json()
            except ValueError:
                result.warnings.append(f"{t['venue']}: wp-json returned non-JSON")
                break
            if not isinstance(posts, list) or not posts:
                break
            for post in posts:
                link = post.get("link") if isinstance(post, dict) else None
                if not link or fetched >= limit:
                    continue
                fetched += 1
                rr = self.safe_fetch(link, result, f"{t['venue']} event page")
                if rr is None:
                    if link in result.blocked:
                        return len(result.events) - before
                    continue
                for it in self.parse(rr.text):
                    it["_page"] = {**t, "url": link}
                    ev = self.normalize(it)
                    if ev and ev.external_id not in seen:
                        seen.add(ev.external_id)
                        result.raw_payloads.append({k: v for k, v in it.items() if k != "_page"})
                        result.events.append(ev)
            if len(posts) < per_page:
                break
            page_no += 1
        return len(result.events) - before

    def normalize(self, it: dict[str, Any]) -> NormalizedEvent | None:
        page = it.get("_page", {})
        d, t = parse_schema_datetime(it.get("startDate") or it.get("start_date") or it.get("date"))
        if not d:
            return None
        de, te = parse_schema_datetime(it.get("endDate") or it.get("end_date"))
        if de and de.year < 1980:  # "1970-01-01" placeholder end dates seen in the wild
            de, te = None, None
        if de and de == d and te == t:
            te = None
        loc = it.get("location") or it.get("venue") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        if isinstance(loc, str):
            loc = {"name": loc}
        if not isinstance(loc, dict):
            loc = {}
        if "venue" in loc and isinstance(loc.get("venue"), str):  # tribe-events venue object
            loc = {"name": loc.get("venue"), "address": {"addressLocality": loc.get("city"), "postalCode": loc.get("zip")}}
        addr = loc.get("address") or {}
        if isinstance(addr, str):
            addr = {"addressLocality": page.get("city")}
        url = it.get("url") or page.get("url")
        name = html_mod.unescape(str(it.get("name") or it.get("title") or "")).strip()
        if not name:
            return None
        ext = hashlib.sha1(f"{page.get('venue') or loc.get('name')}|{name}|{d.isoformat()}|{t or ''}".encode()).hexdigest()[:20]
        offers = it.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        availability = str(offers.get("availability", "")).lower() if isinstance(offers, dict) else ""
        sold_out = "soldout" in availability.replace(" ", "")
        status = normalize_status(it.get("eventStatus"))
        typ = it.get("@type")
        typ = typ[0] if isinstance(typ, list) else typ
        performer = it.get("performer")
        if isinstance(performer, list):
            performer = performer[0] if performer else None
        organizer = it.get("organizer")
        if isinstance(organizer, list):
            organizer = organizer[0] if organizer else None
        locality = (addr.get("addressLocality") or page.get("city") or "").strip(", ")
        return NormalizedEvent(
            source_key=self.name, external_id=ext, title=name[:300], date_start=d, date_end=de, time_start=t, time_end=te,
            category_hint=_merge_hint(str(typ or ""), page.get("category_hint")),
            event_subtype=str(typ) if typ else None,
            venue_name=html_mod.unescape(str((loc.get("name") if page.get("prefer_schema_venue") else None) or page.get("venue") or loc.get("name") or "")).strip() or None,
            city_name=html_mod.unescape(locality) or None,
            postcode=(addr.get("postalCode") or page.get("postcode") or "").strip(", ") or None,
            official_url=url, ticket_url=offers.get("url") if isinstance(offers, dict) else None, source_url=page.get("url") or url,
            organizer=(organizer or {}).get("name") if isinstance(organizer, dict) else (organizer if isinstance(organizer, str) else None),
            status="SOLD_OUT" if sold_out and status == "SCHEDULED" else status, sold_out=sold_out,
            description=(performer or {}).get("name") if isinstance(performer, dict) else None,
            raw={"name": name, "startDate": it.get("startDate"), "endDate": it.get("endDate"), "url": url, "location": loc.get("name"), "type": typ,
                 "eventStatus": it.get("eventStatus"), "availability": availability or None},
        )
