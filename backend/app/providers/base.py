"""Abstract provider contracts. Keep these tiny: the goal is replaceability, not a framework."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventSource(Protocol):
    """Implemented by app.collectors.base.Collector."""
    name: str

    def health_check(self) -> Any: ...
    def collect(self, config: dict[str, Any] | None = None) -> Any: ...


class MapProvider(ABC):
    key: str = "abstract"

    @abstractmethod
    def tile_config(self) -> dict[str, Any]:
        """Return {url, attribution, max_zoom, offline: bool} consumed by the frontend map."""


class NotificationProvider(ABC):
    key: str = "abstract"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def send(self, subject: str, body: str, **kwargs: Any) -> tuple[bool, str]:
        """Return (ok, message). Must never raise — failures are reported, not propagated."""


class StorageProvider(ABC):
    key: str = "abstract"

    @abstractmethod
    def url(self) -> str: ...

    @abstractmethod
    def describe(self) -> dict[str, Any]: ...


class LLMProvider(ABC):
    key: str = "abstract"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str | None:
        """Optional enrichment only. Return None when not configured; callers must degrade gracefully."""


class ExternalDataProvider(ABC):
    """Weather / traffic / transport-disruption / geocoding style feeds used as forecasting features."""
    key: str = "abstract"
    kind: str = "abstract"  # geocoding | weather | traffic | transport

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def fetch(self, **params: Any) -> dict[str, Any] | None: ...
