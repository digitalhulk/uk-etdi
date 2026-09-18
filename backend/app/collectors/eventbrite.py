"""Eventbrite connector. Eventbrite removed public event search from API v3 (2020); with a private token you can
list events for organisations you manage, or fetch specific public event IDs listed in config (event_ids)."""
from __future__ import annotations

from typing import Any, Iterable

from app.processors.normalize import normalize_status, parse_time, parse_uk_date
from app.schemas.normalized import NormalizedEvent

from .base import CollectResult, Collector

BASE = "https://www.eventbriteapi.com/v3"


class EventbriteCollector(Collector):
    name = "eventbrite"
    requires_key = "EVENTBRITE_API_KEY"

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        cfg = {**self.config, **(config or {})}
        result = CollectResult(self.name)
        headers_params = {"token": self.api_key(), "expand": "venue"}
        for eid in cfg.get("event_ids", []) or []:
            try:
                payload = self.fetch(f"{BASE}/events/{eid}/", params=headers_params).json()
            except Exception as exc:
                result.warnings.append(f"event {eid}: {exc}")
                continue
            for item in self.parse(payload):
                result.raw_payloads.append(item)
                ev = self.normalize(item)
                if ev:
                    result.events.append(ev)
        for org in cfg.get("organization_ids", []) or []:
            try:
                payload = self.fetch(f"{BASE}/organizations/{org}/events/", params={**headers_params, "status": "live"}).json()
            except Exception as exc:
                result.warnings.append(f"org {org}: {exc}")
                continue
            for item in self.parse(payload):
                result.raw_payloads.append(item)
                ev = self.normalize(item)
                if ev:
                    result.events.append(ev)
        return result

    def parse(self, payload: Any) -> Iterable[dict[str, Any]]:
        if "events" in payload:
            return payload["events"]
        return [payload] if payload.get("id") else []

    def normalize(self, e: dict[str, Any]) -> NormalizedEvent | None:
        start = (e.get("start") or {}).get("local")
        d = parse_uk_date(start[:10]) if start else None
        if not d:
            return None
        venue = e.get("venue") or {}
        addr = venue.get("address") or {}
        end = (e.get("end") or {}).get("local")
        return NormalizedEvent(
            source_key=self.name, external_id=str(e["id"]), title=(e.get("name") or {}).get("text", ""),
            date_start=d, date_end=parse_uk_date(end[:10]) if end else None,
            time_start=parse_time(start[11:16]) if start else None, time_end=parse_time(end[11:16]) if end else None,
            venue_name=venue.get("name"), city_name=addr.get("city"), postcode=addr.get("postal_code"),
            latitude=float(venue["latitude"]) if venue.get("latitude") else None,
            longitude=float(venue["longitude"]) if venue.get("longitude") else None,
            official_url=e.get("url"), ticket_url=e.get("url"), source_url=e.get("url"),
            status=normalize_status(e.get("status")),
            raw={"id": e.get("id"), "name": (e.get("name") or {}).get("text"), "start": start, "venue": venue.get("name")},
        )
