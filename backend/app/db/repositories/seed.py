"""Seeds reference data (regions, cities, venues, categories, sources) from config/*.yaml. Idempotent."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import categories_config, cities_config, sources_config, venues_config
from app.db.models import Category, City, Region, Source, Venue
from app.processors.normalize import normalize_name


def seed_reference_data(db: Session) -> dict[str, int]:
    counts = {"regions": 0, "cities": 0, "venues": 0, "categories": 0, "sources": 0}

    regions: dict[str, Region] = {r.name: r for r in db.scalars(select(Region)).all()}
    cities: dict[str, City] = {c.normalized_name: c for c in db.scalars(select(City)).all()}
    for c in cities_config():
        rname = c.get("region") or "Unknown"
        if rname not in regions:
            regions[rname] = Region(name=rname, country=c.get("country", "England"))
            db.add(regions[rname])
            db.flush()
            counts["regions"] += 1
        key = normalize_name(c["name"])
        city = cities.get(key)
        if not city:
            city = City(name=c["name"], normalized_name=key)
            db.add(city)
            cities[key] = city
            counts["cities"] += 1
        city.region_id = regions[rname].id
        city.country = c.get("country", "England")
        city.latitude, city.longitude = c.get("latitude"), c.get("longitude")
        city.population, city.population_source = c.get("population"), c.get("population_source")
        city.priority = c.get("priority", 50)
        city.tourism = c.get("tourism", 0.3)
        city.aliases = c.get("aliases") or []
    db.flush()

    venues: dict[str, Venue] = {v.normalized_name: v for v in db.scalars(select(Venue)).all()}
    for v in venues_config():
        key = normalize_name(v["name"])
        venue = venues.get(key)
        if not venue:
            venue = Venue(name=v["name"], normalized_name=key)
            db.add(venue)
            venues[key] = venue
            counts["venues"] += 1
        city = cities.get(normalize_name(v.get("city", "")))
        venue.city_id = city.id if city else None
        venue.aliases = v.get("aliases") or []
        venue.postcode = v.get("postcode")
        venue.latitude, venue.longitude = v.get("latitude"), v.get("longitude")
        venue.capacity, venue.capacity_source = v.get("capacity"), v.get("capacity_source")
        venue.venue_type = v.get("venue_type")
        venue.station_distance_km = v.get("station_distance_km")
        venue.airport_distance_km = v.get("airport_distance_km")
        venue.is_seeded = True
        venue.importance_score = _importance(v)
    db.flush()

    existing_cats = {(c.name, c.subcategory) for c in db.scalars(select(Category)).all()}
    for rule in categories_config().get("categories", []):
        k = (rule["category"], rule.get("subcategory"))
        if k not in existing_cats:
            db.add(Category(name=k[0], subcategory=k[1]))
            existing_cats.add(k)
            counts["categories"] += 1
    if ("other", "general") not in existing_cats:
        db.add(Category(name="other", subcategory="general"))

    sources = {s.key: s for s in db.scalars(select(Source)).all()}
    for key, cfg in sources_config().items():
        s = sources.get(key)
        if not s:
            s = Source(key=key, name=key.replace("_", " ").title(), type=cfg.get("type", "api"), enabled=bool(cfg.get("enabled", True)))
            db.add(s)
            sources[key] = s
            counts["sources"] += 1
        s.type = cfg.get("type", s.type)
        s.priority = cfg.get("priority", 50)
        # NOTE: `enabled` is seeded once; afterwards the dashboard/API toggle (persisted in DB) is authoritative.
        s.config = {k: v for k, v in cfg.items() if k not in ("enabled", "priority", "type")}
    db.commit()
    return counts


def _importance(v: dict) -> float:
    cap = v.get("capacity") or 0
    base = min(cap / 60000, 1.0)
    if v.get("venue_type") in ("stadium", "arena"):
        base = min(base + 0.1, 1.0)
    return round(base, 3)
