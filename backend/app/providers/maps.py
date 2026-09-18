from __future__ import annotations

from typing import Any

from app.core.config import get_settings

from .base import MapProvider


class OSMTileProvider(MapProvider):
    """Default: OpenStreetMap-compatible XYZ tiles (free). MAP_TILE_URL overrides for any self-hosted / alternative server."""
    key = "osm"

    def tile_config(self) -> dict[str, Any]:
        s = get_settings()
        url = getattr(s, "map_tile_url", "") or "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution = getattr(s, "map_tile_attribution", "") or "© OpenStreetMap contributors"
        return {"provider": self.key, "url": url, "attribution": attribution, "max_zoom": 18, "offline": False}


class OfflineMapProvider(MapProvider):
    """No tiles at all: the frontend renders markers on a plain UK-bounds canvas. Used when MAP_PROVIDER=offline."""
    key = "offline"

    def tile_config(self) -> dict[str, Any]:
        return {"provider": self.key, "url": None, "attribution": "", "max_zoom": 0, "offline": True}
