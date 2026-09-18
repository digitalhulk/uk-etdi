from __future__ import annotations

from typing import Any

from app.core.config import get_settings

from .base import StorageProvider


class SQLAlchemyStorage(StorageProvider):
    """SQLite by default (zero cost). Any SQLAlchemy URL works: postgresql://, mysql://… via DATABASE_URL."""
    key = "sqlalchemy"

    def url(self) -> str:
        return get_settings().database_url

    def describe(self) -> dict[str, Any]:
        u = self.url()
        return {"provider": self.key, "scheme": u.split(":", 1)[0], "sqlite": u.startswith("sqlite")}
