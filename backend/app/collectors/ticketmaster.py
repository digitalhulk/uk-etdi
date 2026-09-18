"""Ticketmaster Discovery API v2 (free tier: 5000 req/day). Requires TICKETMASTER_API_KEY."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from app.processors.normalize import normalize_status, parse_time, parse_uk_date, split_local
from app.schemas.normalized import NormalizedEvent

from .base import CollectResult, Collector, HealthResult

BASE = "https://app.ticketmaster.com/discovery/v2/events.json"


class TicketmasterCollector(Collector):
    name = "ticketmaster"
    requires_key = "TICKETMASTER_API_KEY"

    def health_check(self) -> HealthResult:
        if not self.api_key():
            return HealthResult("DISABLED", "TICKETMASTER_API_KEY not configured")
        try:
            r = self.fetch(BASE, params={"apikey": self.api_key(), "countryCode": "GB", "size": 1})
            return HealthResult("HEALTHY", "ok", int(r.elapsed.total_seconds() * 1000))
        except Exception as exc:
            return HealthResult("FAILED", str(exc)[:200])

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        cfg = {**self.config, **(config or {})}
        result = CollectResult(self.name)
        days = int(cfg.get("days_ahead", 60))
        start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for page in range(int(cfg.get("max_pages", 5))):
            params = {"apikey": self.api_key(), "countryCode": cfg.get("country_code", "GB"), "size": int(cfg.get("page_size", 200)),
                      "page": page, "startDateTime": start, "endDateTime": end, "sort": "date,asc"}
            try:
                payload = self.fetch(BASE, params=params).json()
            except Exception as exc:
                result.warnings.append(f"page {page}: {exc}")
                break
            items = list(self.parse(payload))
            result.raw_payloads.extend(items)
            for item in items:
                ev = self.normalize(item)
                if ev:
                    result.events.append(ev)
            total_pages = payload.get("page", {}).get("totalPages", 1)
            if page + 1 >= total_pages or page + 1 >= 5:  # TM caps deep paging at 1000 items
                break
        return result

    def parse(self, payload: Any) -> Iterable[dict[str, Any]]:
        return payload.get("_embedded", {}).get("events", []) or []

    def normalize(self, e: dict[str, Any]) -> NormalizedEvent | None:
        dates = e.get("dates", {})
        start = dates.get("start", {})
        d = parse_uk_date(start.get("localDate"))
        if not d:
            if start.get("dateTime"):
                d, _ = split_local(datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")))
            else:
                return None
        t = parse_time(start.get("localTime")) if not start.get("timeTBA") else None
        venue = (e.get("_embedded", {}).get("venues") or [{}])[0]
        loc = venue.get("location", {})
        classification = (e.get("classifications") or [{}])[0]
        hint = " ".join(filter(None, [classification.get("segment", {}).get("name"), classification.get("genre", {}).get("name")]))
        return NormalizedEvent(
            source_key=self.name, external_id=e["id"], title=e.get("name", ""), category_hint=hint or None,
            date_start=d, date_end=parse_uk_date(dates.get("end", {}).get("localDate")), time_start=t,
            time_end=parse_time(dates.get("end", {}).get("localTime")),
            venue_name=venue.get("name"), city_name=venue.get("city", {}).get("name"),
            postcode=venue.get("postalCode"), latitude=float(loc["latitude"]) if loc.get("latitude") else None,
            longitude=float(loc["longitude"]) if loc.get("longitude") else None,
            organizer=(e.get("promoter") or {}).get("name"), official_url=e.get("url"), ticket_url=e.get("url"),
            source_url=e.get("url"), status=normalize_status(dates.get("status", {}).get("code")),
            raw={"id": e.get("id"), "name": e.get("name"), "dates": dates, "venue": venue.get("name"), "url": e.get("url"),
                 "classification": hint},
        )
