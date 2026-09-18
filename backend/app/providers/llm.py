from __future__ import annotations

from typing import Any

from .base import LLMProvider


class NullLLM(LLMProvider):
    """The platform is fully deterministic; an LLM is optional enrichment only. This provider is always 'not configured'."""
    key = "null"

    def is_configured(self) -> bool:
        return False

    def complete(self, prompt: str, **kwargs: Any) -> str | None:
        return None
