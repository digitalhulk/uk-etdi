"""Curated local file of manually verified official events (data/curated_events.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from app.core.config import ROOT_DIR
from app.processors.normalize import parse_time, parse_uk_date
from app.schemas.normalized import NormalizedEvent

from .base import CollectResult, Collector


class CuratedCollector(Collector):
    source_confidence = "CURATED"
    name = "curated"

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        cfg = {**self.config, **(config or {})}
        result = CollectResult(self.name)
        path = Path(cfg.get("path", "data/curated_events.json"))
        if not path.is_absolute():
            path = ROOT_DIR / path
        if not path.exists():
            result.warnings.append(f"{path} missing")
            return result
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in self.parse(payload):
            result.raw_payloads.append(item)
            ev = self.normalize(item)
            if ev:
                result.events.append(ev)
        return result

    def parse(self, payload: Any) -> Iterable[dict[str, Any]]:
        return payload if isinstance(payload, list) else []

    def normalize(self, it: dict[str, Any]) -> NormalizedEvent | None:
        d = parse_uk_date(it.get("date_start"))
        if not d:
            return None
        return NormalizedEvent(
            source_key=self.name, external_id=it["external_id"], title=it["title"], category_hint=it.get("category_hint"),
            date_start=d, date_end=parse_uk_date(it.get("date_end")), time_start=parse_time(it.get("time_start")),
            time_end=parse_time(it.get("time_end")), venue_name=it.get("venue"), city_name=it.get("city"),
            postcode=it.get("postcode"), organizer=it.get("organizer"), official_url=it.get("official_url"),
            ticket_url=it.get("ticket_url"), source_url=it.get("official_url"), status=it.get("status", "SCHEDULED"),
            venue_capacity=it.get("capacity"), raw=it,
        )
