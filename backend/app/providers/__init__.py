"""Provider abstraction (section 6). Every external dependency is reached through one of these interfaces so the
concrete implementation can be swapped by configuration without touching business logic.

    EventSource          → app.collectors.base.Collector (registry: app.collectors.registry.COLLECTORS)
    MapProvider          → app.providers.maps           (OSM tiles by default; any XYZ tile server; offline fallback)
    NotificationProvider → app.providers.notifications  (Telegram default; console/no-op; email when configured)
    StorageProvider      → app.providers.storage        (SQLAlchemy URL — SQLite default, Postgres/MySQL by DATABASE_URL)
    LLMProvider          → app.providers.llm            (NullLLM default: the platform never requires an LLM)
    ExternalDataProvider → app.providers.external_data  (geocoding = postcodes.io; weather/traffic = null until configured)
"""
from .base import EventSource, ExternalDataProvider, LLMProvider, MapProvider, NotificationProvider, StorageProvider  # noqa: F401
from .registry import get_external_data_provider, get_llm_provider, get_map_provider, get_notification_providers, get_storage_provider  # noqa: F401
