"""Configuration manager: env-driven settings + YAML config loaders (cached)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent
CONFIG_DIR = Path(os.getenv("UK_ETDI_CONFIG_DIR", ROOT_DIR / "config"))
DATA_DIR = Path(os.getenv("UK_ETDI_DATA_DIR", ROOT_DIR / "data"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "UK-ETDI"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = f"sqlite:///{DATA_DIR / 'uk_etdi.db'}"
    api_admin_token: str = ""
    default_timezone: str = "Europe/London"
    service_area_cities: str = "London,Manchester,Birmingham,Leeds,Liverpool"
    home_city: str = "London"
    http_timeout_seconds: float = 20.0
    http_user_agent: str = "UK-ETDI/0.1 (+public event intelligence; respects robots.txt)"
    # retention (days) — bounded SQLite growth; canonical events are never deleted
    retention_raw_days: int = 30
    retention_snapshot_days: int = 180
    retention_health_days: int = 60
    retention_runs_days: int = 365

    ticketmaster_api_key: str = ""
    eventbrite_api_key: str = ""
    jambase_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    google_sheets_webhook: str = ""
    # provider selection (section 6) — all defaults are free
    map_provider: str = "osm"            # osm | offline
    map_tile_url: str = ""               # any XYZ tile server; blank = OpenStreetMap
    map_tile_attribution: str = ""
    notification_providers: str = "telegram"  # comma list: telegram,email,console

    @property
    def service_area(self) -> list[str]:
        return [c.strip() for c in self.service_area_cities.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()


def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache
def load_config(name: str) -> dict[str, Any]:
    return _load_yaml(name)


def sources_config() -> dict[str, Any]:
    return load_config("sources.yaml").get("sources", {})


def categories_config() -> dict[str, Any]:
    return load_config("categories.yaml")


def cities_config() -> list[dict[str, Any]]:
    return load_config("cities.yaml").get("cities", [])


def venues_config() -> list[dict[str, Any]]:
    return load_config("venues.yaml").get("venues", [])


def scoring_config() -> dict[str, Any]:
    return load_config("scoring.yaml")


def reload_configs() -> None:
    load_config.cache_clear()
