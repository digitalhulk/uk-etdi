"""Geography engine: resolves venue + city for an event using the seeded registry (exact, alias, fuzzy), postcode
and coordinates. Optionally uses the free postcodes.io API for postcode -> lat/lon (no key; rate-limited)."""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import City, Venue
from app.processors.normalize import normalize_name, normalize_postcode
from app.schemas.normalized import NormalizedEvent

log = get_logger("geo")


@dataclass
class GeoResolution:
    venue: Venue | None
    city: City | None
    latitude: float | None
    longitude: float | None
    postcode: str | None
    method: str


class GeographyEngine:
    def __init__(self, db: Session, use_postcode_api: bool = False):
        self.db = db
        self.use_postcode_api = use_postcode_api
        self._venues = db.scalars(select(Venue)).all()
        self._cities = db.scalars(select(City)).all()
        self._venue_index: dict[str, Venue] = {}
        # seeded venues (with sourced capacity) win over auto-created ones, including via aliases
        for v in sorted(self._venues, key=lambda x: not x.is_seeded):
            if v.is_seeded:
                self._venue_index[v.normalized_name] = v
                for a in v.aliases or []:
                    self._venue_index[normalize_name(a)] = v
            else:
                self._venue_index.setdefault(v.normalized_name, v)
        self._city_index: dict[str, City] = {}
        for c in self._cities:
            self._city_index[c.normalized_name] = c
            for a in c.aliases or []:
                self._city_index.setdefault(normalize_name(a), c)
        self._postcode_cache: dict[str, tuple[float, float] | None] = {}

    # ---- venues -----------------------------------------------------------------------------------------
    def match_venue(self, name: str | None, city_hint: str | None = None) -> tuple[Venue | None, str]:
        if not name or normalize_name(name) in {"tbd", "tba", "tbc", "venue tbc", "to be confirmed"}:
            return None, "no_venue"
        key = normalize_name(name)
        if key in self._venue_index:
            return self._venue_index[key], "venue_exact"
        # containment (e.g. "Wembley Stadium connected by EE")
        for k, v in self._venue_index.items():
            if len(k) > 5 and (k in key or key in k):
                return v, "venue_contains"
        choices = list(self._venue_index.keys())
        best = process.extractOne(key, choices, scorer=fuzz.token_set_ratio)
        if best and best[1] >= 90:
            return self._venue_index[best[0]], f"venue_fuzzy_{int(best[1])}"
        return None, "venue_unmatched"

    def match_city(self, name: str | None) -> tuple[City | None, str]:
        if not name:
            return None, "no_city"
        key = normalize_name(name)
        if key in self._city_index:
            return self._city_index[key], "city_exact"
        # "Greater London" / "London Borough of X"
        for k, c in self._city_index.items():
            if k and (f" {k} " in f" {key} "):
                return c, "city_contains"
        best = process.extractOne(key, list(self._city_index.keys()), scorer=fuzz.ratio)
        if best and best[1] >= 88:
            return self._city_index[best[0]], f"city_fuzzy_{int(best[1])}"
        return None, "city_unmatched"

    def nearest_city(self, lat: float, lon: float) -> City | None:
        best, best_d = None, 1e9
        for c in self._cities:
            if c.latitude is None:
                continue
            d = (c.latitude - lat) ** 2 + (c.longitude - lon) ** 2
            if d < best_d:
                best, best_d = c, d
        return best if best_d < 0.25 else None  # ~35km box

    def lookup_postcode(self, pc: str) -> tuple[float, float] | None:
        if not self.use_postcode_api:
            return None
        if pc in self._postcode_cache:
            return self._postcode_cache[pc]
        try:
            r = httpx.get(f"https://api.postcodes.io/postcodes/{pc.replace(' ', '')}", timeout=8)
            res = r.json().get("result") if r.status_code == 200 else None
            val = (res["latitude"], res["longitude"]) if res else None
        except Exception:
            val = None
        self._postcode_cache[pc] = val
        return val

    def resolve(self, ev: NormalizedEvent) -> GeoResolution:
        venue, method = self.match_venue(ev.venue_name, ev.city_name)
        city = venue.city if venue and venue.city else None
        if city is None:
            city, cm = self.match_city(ev.city_name)
            method = f"{method}+{cm}"
        lat, lon = ev.latitude, ev.longitude
        postcode = normalize_postcode(ev.postcode) or (venue.postcode if venue else None)
        if lat is None and venue and venue.latitude is not None:
            lat, lon = venue.latitude, venue.longitude
        if lat is None and postcode:
            coords = self.lookup_postcode(postcode)
            if coords:
                lat, lon = coords
                method += "+postcode_api"
        if city is None and lat is not None:
            city = self.nearest_city(lat, lon)
            if city:
                method += "+nearest_city"
        if lat is None and city and city.latitude is not None:
            lat, lon = city.latitude, city.longitude
            method += "+city_centroid"
        return GeoResolution(venue, city, lat, lon, postcode, method)

    def get_or_create_venue(self, ev: NormalizedEvent, geo: GeoResolution) -> Venue | None:
        """Creates a lightweight venue record for unmatched but named venues (capacity left NULL — never invented)."""
        if geo.venue or not ev.venue_name:
            return geo.venue
        key = normalize_name(ev.venue_name)
        if not key or key in {"tbd", "tba", "tbc", "venue tbc", "to be confirmed"}:
            return None
        v = Venue(name=ev.venue_name[:200], normalized_name=key, city_id=geo.city.id if geo.city else None,
                  postcode=geo.postcode, latitude=ev.latitude, longitude=ev.longitude, capacity=ev.venue_capacity,
                  capacity_source="source_provided" if ev.venue_capacity else None, venue_type="unknown", is_seeded=False)
        self.db.add(v)
        self.db.flush()
        self._venue_index[key] = v
        self._venues.append(v)
        return v
