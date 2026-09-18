"""Service-area resolution: Settings table (`service_area_cities`, `service_area_radius_km`, `home_city`) overrides env.
No user-specific area is hardcoded: the env default is a generic UK-metro list documented in .env.example and the
dashboard Settings page can replace it at runtime (admin token required)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.processors.normalize import normalize_name

_cache: dict[str, Any] = {}


def load_service_area(db: Session | None) -> dict[str, Any]:
    """Returns {"cities": [...], "normalized": set, "radius_km": float|None, "home_city": str|None, "source": "settings"|"env"}."""
    s = get_settings()
    cities, radius, home, origin = list(s.service_area), None, s.home_city or None, "env"
    if db is not None:
        try:
            from app.db.models import Setting
            rows = {r.key: r.value for r in db.scalars(select(Setting).where(Setting.key.in_(["service_area_cities", "service_area_radius_km", "home_city", "service_area"]))).all()}
            sa_obj = rows.get("service_area") or {}
            if isinstance(sa_obj, dict):  # §27 structured object: priority_cities + primary_city define the area
                pc = [str(c) for c in (sa_obj.get("priority_cities") or []) if c]
                if sa_obj.get("primary_city"):
                    pc = [str(sa_obj["primary_city"])] + [c for c in pc if c != sa_obj["primary_city"]]
                if pc:
                    rows.setdefault("service_area_cities", pc)
                if sa_obj.get("radius_miles") is not None:
                    rows.setdefault("service_area_radius_km", float(sa_obj["radius_miles"]) * 1.609)
                if sa_obj.get("primary_city"):
                    rows.setdefault("home_city", sa_obj["primary_city"])
            v = rows.get("service_area_cities")
            if isinstance(v, str):
                v = [c.strip() for c in v.split(",") if c.strip()]
            if isinstance(v, list) and v:
                cities, origin = [str(c) for c in v], "settings"
            if rows.get("service_area_radius_km") is not None:
                radius = float(rows["service_area_radius_km"])
            if rows.get("home_city"):
                home = str(rows["home_city"])
        except Exception:
            pass
    extra = {}
    if db is not None:
        try:
            extra = {k: (rows.get("service_area") or {}).get(k) or [] for k in ("priority_postcodes", "airports", "stations", "venues")}
        except Exception:
            extra = {}
    out = {"cities": cities, "normalized": {normalize_name(c) for c in cities}, "radius_km": radius, "home_city": home, "source": origin, **extra}
    _cache.clear()
    _cache.update(out)
    return out


def current() -> dict[str, Any]:
    return _cache if _cache else load_service_area(None)
