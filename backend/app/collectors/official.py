"""Official fixture feeds (football / rugby) — public JSON from fixturedownload.com (no key). Kick-off times are UTC and
converted to Europe/London. Venue → city is resolved via the venue registry in config/venues.yaml."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Iterable

from app.core.config import venues_config
from app.processors.normalize import normalize_name, split_local
from app.schemas.normalized import NormalizedEvent

from .base import CollectResult, Collector


class FootballFixturesCollector(Collector):
    """Official-league fixture feeds (fixturedownload.com republishes official schedules as JSON). Named
    `football_fixtures` for backward compatibility; also carries rugby/cricket/other feeds listed in sources.yaml."""
    name = "football_fixtures"
    source_confidence = "TRUSTED"
    _uk_venues: set[str] | None = None

    @classmethod
    def uk_venue_names(cls) -> set[str]:
        if cls._uk_venues is None:
            names = set()
            for v in venues_config():
                names.add(normalize_name(v["name"]))
                names.update(normalize_name(a) for a in v.get("aliases", []) or [])
            cls._uk_venues = names
        return cls._uk_venues

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:
        cfg = {**self.config, **(config or {})}
        result = CollectResult(self.name)
        feeds = cfg.get("feeds", []) or []
        ok = 0
        wanted_sport = (self.filters or {}).get("sport")
        for feed in feeds:
            if wanted_sport and feed.get("sport") != wanted_sport:
                continue
            r = self.safe_fetch(feed["url"], result, feed.get("name"), check_robots=False)
            if r is None:
                continue
            try:
                payload = r.json()
            except ValueError:
                result.warnings.append(f"{feed.get('name')}: non-JSON")
                continue
            ok += 1
            for item in self.parse(payload):
                item["_feed"] = feed
                result.raw_payloads.append(item)
                ev = self.normalize(item)
                if ev:
                    result.events.append(ev)
        return result

    def parse(self, payload: Any) -> Iterable[dict[str, Any]]:
        return payload if isinstance(payload, list) else []

    def normalize(self, m: dict[str, Any]) -> NormalizedEvent | None:
        feed = m.get("_feed", {})
        raw_dt = m.get("DateUtc")
        if not raw_dt:
            return None
        dt = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M:%SZ")
        d, t = split_local(dt)
        home, away = m.get("HomeTeam", ""), m.get("AwayTeam", "")
        if not home or not away or "to be announced" in (home + away).lower():
            return None
        title = f"{home} v {away}"
        comp = feed.get("competition", "")
        loc = (m.get("Location") or "").strip()
        if feed.get("uk_only") and normalize_name(loc) not in self.uk_venue_names():
            return None  # mixed-country competition: keep only fixtures at venues in the UK venue registry
        ext = hashlib.sha1(f"{feed.get('url')}|{m.get('MatchNumber')}|{home}|{away}".encode()).hexdigest()[:20]
        # Placeholder 00:00 kickoffs mean "time TBC" in this feed
        return NormalizedEvent(
            source_key=self.name, external_id=ext, title=title, category_hint=f"{feed.get('sport','football')} {comp}",
            description=f"{comp} round {m.get('RoundNumber')}", date_start=d,
            time_start=None if t == "00:00" else t, venue_name=None if (m.get("Location") or "").strip().upper() in ("TBD", "TBA", "TBC", "") else m.get("Location"),
            organizer=comp, city_name=feed.get("city"),
            source_url=feed.get("url"), status="COMPLETED" if m.get("HomeTeamScore") is not None else "SCHEDULED",
            recurrence="fixture",
            raw={k: v for k, v in m.items() if k != "_feed"},
        )
