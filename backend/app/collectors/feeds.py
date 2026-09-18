"""Generic iCal and RSS feed collectors (councils, universities, venues publish these publicly)."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from dateutil import parser as dtparser
from icalendar import Calendar

from app.processors.normalize import parse_time, parse_uk_date, split_local
from app.schemas.normalized import NormalizedEvent

from .base import CollectResult, Collector


class ICalFeedCollector(Collector):
    name = "ical_feeds"

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        cfg = {**self.config, **(config or {})}
        result = CollectResult(self.name)
        for feed in cfg.get("feeds", []) or []:
            r = self.safe_fetch(feed["url"], result, feed.get("name") or feed["url"])
            if r is None:
                continue
            text = r.text
            try:
                items = list(self.parse(text))
            except Exception as exc:
                result.warnings.append(f"{feed.get('name')}: parse error {type(exc).__name__}")
                continue
            for item in items:
                item["_feed"] = feed
                result.raw_payloads.append(item)
                ev = self.normalize(item)
                if ev:
                    result.events.append(ev)
        return result

    def parse(self, text: str) -> Iterable[dict[str, Any]]:
        cal = Calendar.from_ical(text)
        for comp in cal.walk("VEVENT"):
            yield {k.lower(): str(comp.get(k)) if k != "DTSTART" and k != "DTEND" else comp.get(k).dt for k in comp.keys()
                   if k in ("UID", "SUMMARY", "DTSTART", "DTEND", "LOCATION", "URL", "STATUS", "CATEGORIES", "DESCRIPTION")}

    def normalize(self, it: dict[str, Any]) -> NormalizedEvent | None:
        feed = it.get("_feed", {})
        ds = it.get("dtstart")
        if ds is None:
            return None
        t = None
        if isinstance(ds, datetime):
            d, t = split_local(ds) if ds.tzinfo else (ds.date(), ds.strftime("%H:%M"))
        else:
            d = ds
        de = it.get("dtend")
        date_end, time_end = None, None
        if isinstance(de, datetime):
            date_end, time_end = split_local(de) if de.tzinfo else (de.date(), de.strftime("%H:%M"))
        elif isinstance(de, date):
            date_end = de
        ext = hashlib.sha1(f"{feed.get('url')}|{it.get('uid')}".encode()).hexdigest()[:20]
        return NormalizedEvent(
            source_key=self.name, external_id=ext, title=it.get("summary", ""), category_hint=it.get("categories") or feed.get("category_hint"),
            date_start=d, date_end=date_end, time_start=t, time_end=time_end, venue_name=it.get("location") or feed.get("venue"),
            city_name=feed.get("city"), official_url=it.get("url"), source_url=feed.get("url"),
            status="CANCELLED" if str(it.get("status", "")).upper() == "CANCELLED" else "SCHEDULED",
            organizer=feed.get("organizer"), raw={"uid": it.get("uid"), "summary": it.get("summary"), "dtstart": str(ds)},
        )


class RSSFeedCollector(Collector):
    name = "rss_feeds"
    _date_re = re.compile(r"(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})")

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        cfg = {**self.config, **(config or {})}
        result = CollectResult(self.name)
        for feed in cfg.get("feeds", []) or []:
            r = self.safe_fetch(feed["url"], result, feed.get("name") or feed["url"])
            if r is None:
                continue
            text = r.text
            try:
                items = list(self.parse(text))
            except Exception as exc:
                result.warnings.append(f"{feed.get('name')}: parse error {type(exc).__name__}")
                continue
            for item in items:
                item["_feed"] = feed
                result.raw_payloads.append(item)
                ev = self.normalize(item)
                if ev:
                    result.events.append(ev)
        return result

    def parse(self, text: str) -> Iterable[dict[str, Any]]:
        root = ET.fromstring(text.encode("utf-8"))
        ns = {"ev": "http://purl.org/rss/1.0/modules/event/", "atom": "http://www.w3.org/2005/Atom"}
        for item in root.iter("item"):
            yield {
                "title": (item.findtext("title") or "").strip(), "link": item.findtext("link"),
                "guid": item.findtext("guid") or item.findtext("link"), "description": item.findtext("description") or "",
                "startdate": item.findtext("ev:startdate", namespaces=ns), "enddate": item.findtext("ev:enddate", namespaces=ns),
                "location": item.findtext("ev:location", namespaces=ns), "pubdate": item.findtext("pubDate"),
            }

    # Spektrix-style feeds put the performance date/time in the title: "The Ferry | 20 February 2027 (19:30PM)"
    _title_dt_re = re.compile(r"^(?P<title>.+?)\s*\|\s*(?P<date>\d{1,2}\s+\w+\s+\d{4})\s*(?:\((?P<time>\d{1,2}[:.]\d{2})\s*(?:AM|PM|am|pm)?\))?\s*$")

    def normalize(self, it: dict[str, Any]) -> NormalizedEvent | None:
        feed = it.get("_feed", {})
        title = (it.get("title") or "").strip()
        if not title:
            return None
        time_start = None
        d = parse_uk_date(it.get("startdate"))
        m = self._title_dt_re.match(title)
        if m:
            title = m.group("title").strip()
            d = d or parse_uk_date(m.group("date"))
            time_start = parse_time(m.group("time")) if m.group("time") else None
        if not d and feed.get("pubdate_is_start"):
            d = parse_uk_date(it.get("pubdate"))
            if d:
                try:
                    time_start = dtparser.parse(it["pubdate"]).strftime("%H:%M")
                except Exception:
                    time_start = None
                if time_start == "00:00":
                    time_start = None
        if not d:
            if feed.get("strict_dates", True):
                return None  # news/blog items without an explicit event date are not events
            m2 = self._date_re.search(f"{title} {it.get('description','')}")
            d = parse_uk_date(m2.group(1)) if m2 else None
        if not d:
            return None
        ext = hashlib.sha1(f"{feed.get('url')}|{it.get('guid') or title}|{d.isoformat()}|{time_start or ''}".encode()).hexdigest()[:20]
        return NormalizedEvent(
            source_key=self.name, external_id=ext, title=title[:300], date_start=d, date_end=parse_uk_date(it.get("enddate")), time_start=time_start,
            venue_name=it.get("location") or feed.get("venue"), city_name=feed.get("city"), official_url=it.get("link") or feed.get("website"),
            source_url=feed.get("url"), category_hint=feed.get("category_hint"),
            raw={"guid": it.get("guid"), "title": it.get("title"), "link": it.get("link")},
        )
