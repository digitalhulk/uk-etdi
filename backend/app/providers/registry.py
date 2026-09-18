"""Provider selection by settings. Add a new implementation → register it here → select it via env."""
from __future__ import annotations

from app.core.config import get_settings

from .base import ExternalDataProvider, LLMProvider, MapProvider, NotificationProvider, StorageProvider
from .external_data import NullExternalData, PostcodesIOGeocoder
from .llm import NullLLM
from .maps import OfflineMapProvider, OSMTileProvider
from .notifications import ConsoleProvider, EmailProvider, TelegramProvider
from .storage import SQLAlchemyStorage

_MAPS: dict[str, type[MapProvider]] = {"osm": OSMTileProvider, "offline": OfflineMapProvider}
_NOTIFY: dict[str, type[NotificationProvider]] = {"telegram": TelegramProvider, "email": EmailProvider, "console": ConsoleProvider}
_EXTERNAL: dict[str, type[ExternalDataProvider]] = {"postcodes_io": PostcodesIOGeocoder}


def get_map_provider() -> MapProvider:
    key = (getattr(get_settings(), "map_provider", "") or "osm").lower()
    return _MAPS.get(key, OSMTileProvider)()


def get_notification_providers() -> list[NotificationProvider]:
    keys = [k.strip().lower() for k in (getattr(get_settings(), "notification_providers", "") or "telegram").split(",") if k.strip()]
    return [_NOTIFY[k]() for k in keys if k in _NOTIFY]


def get_storage_provider() -> StorageProvider:
    return SQLAlchemyStorage()


def get_llm_provider() -> LLMProvider:
    return NullLLM()


def get_external_data_provider(kind: str) -> ExternalDataProvider:
    if kind == "geocoding":
        return PostcodesIOGeocoder()
    return NullExternalData(kind)


def providers_status() -> dict:
    """For /api/health/detailed and the System page. Never includes secrets."""
    return {
        "map": get_map_provider().tile_config() | {"available": list(_MAPS)},
        "notifications": [{"key": p.key, "configured": p.is_configured()} for p in get_notification_providers()],
        "storage": get_storage_provider().describe(),
        "llm": {"key": get_llm_provider().key, "configured": get_llm_provider().is_configured()},
        "external_data": [{"kind": k, "key": get_external_data_provider(k).key, "configured": get_external_data_provider(k).is_configured()}
                          for k in ("geocoding", "weather", "traffic", "transport")],
    }
