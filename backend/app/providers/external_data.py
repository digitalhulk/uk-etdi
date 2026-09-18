from __future__ import annotations

from typing import Any

import httpx

from app.core.netsafe import validate_url

from .base import ExternalDataProvider


class PostcodesIOGeocoder(ExternalDataProvider):
    """Free UK postcode geocoding (api.postcodes.io). Used only when a venue has a postcode but no coordinates."""
    key, kind = "postcodes_io", "geocoding"

    def is_configured(self) -> bool:
        return True

    def fetch(self, **params: Any) -> dict[str, Any] | None:
        pc = str(params.get("postcode") or "").replace(" ", "")
        if not pc:
            return None
        url = f"https://api.postcodes.io/postcodes/{pc}"
        try:
            validate_url(url, ["api.postcodes.io"])
            r = httpx.get(url, timeout=8)
            if r.status_code != 200:
                return None
            d = r.json().get("result") or {}
            return {"latitude": d.get("latitude"), "longitude": d.get("longitude"), "region": d.get("region"), "admin_district": d.get("admin_district")}
        except Exception:
            return None


class NullExternalData(ExternalDataProvider):
    """Placeholder for weather / traffic / transport disruption feeds. Reports itself as not configured so the
    forecasting feature pipeline records these features as null rather than inventing them."""
    key = "null"

    def __init__(self, kind: str):
        self.kind = kind

    def is_configured(self) -> bool:
        return False

    def fetch(self, **params: Any) -> dict[str, Any] | None:
        return None
