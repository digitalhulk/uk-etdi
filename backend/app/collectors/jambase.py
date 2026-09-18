"""JamBase Events API (free developer tier). Requires JAMBASE_API_KEY."""
from __future__ import annotations

from typing import Any, Iterable

from app.processors.normalize import normalize_status, parse_time, parse_uk_date
from app.schemas.normalized import NormalizedEvent

from .base import CollectResult, Collector

BASE = "https://www.jambase.com/jb-api/v1/events"


class JamBaseCollector(Collector):
    name = "jambase"
    requires_key = "JAMBASE_API_KEY"

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        result = CollectResult(self.name)
        page = 1
        while page <= 5:
            try:
                payload = self.fetch(BASE, params={"apikey": self.api_key(), "geoCountryIso2": "GB", "perPage": 100, "page": page}).json()
            except Exception as exc:
                result.warnings.append(f"page {page}: {exc}")
                break
            items = list(self.parse(payload))
            if not items:
                break
            result.raw_payloads.extend(items)
            result.events.extend(filter(None, (self.normalize(i) for i in items)))
            if page >= int(payload.get("pagination", {}).get("totalPages", 1)):
                break
            page += 1
        return result

    def parse(self, payload: Any) -> Iterable[dict[str, Any]]:
        return payload.get("events", []) or []

    def normalize(self, e: dict[str, Any]) -> NormalizedEvent | None:
        start = e.get("startDate")
        d = parse_uk_date(start[:10]) if start else None
        if not d:
            return None
        loc = e.get("location") or {}
        addr = loc.get("address") or {}
        geo = loc.get("geo") or {}
        return NormalizedEvent(
            source_key=self.name, external_id=str(e.get("identifier") or e.get("@id")), title=e.get("name", ""),
            category_hint="concert", date_start=d, time_start=parse_time(start[11:16]) if start and len(start) > 15 else None,
            venue_name=loc.get("name"), city_name=addr.get("addressLocality"), postcode=addr.get("postalCode"),
            latitude=geo.get("latitude"), longitude=geo.get("longitude"), official_url=e.get("url"),
            ticket_url=(e.get("offers") or [{}])[0].get("url") if e.get("offers") else None, source_url=e.get("url"),
            status=normalize_status(e.get("eventStatus")),
            raw={"id": e.get("identifier"), "name": e.get("name"), "startDate": start, "venue": loc.get("name")},
        )
