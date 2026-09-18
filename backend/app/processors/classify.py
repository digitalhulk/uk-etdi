"""Deterministic keyword classifier driven by config/categories.yaml."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import categories_config


@lru_cache
def _rules() -> list[tuple[str, str, tuple[str, ...]]]:
    rules = []
    for r in categories_config().get("categories", []):
        kws = tuple(sorted((k.lower() for k in r.get("keywords", [])), key=len, reverse=True))
        rules.append((r["category"], r.get("subcategory") or "general", kws))
    return rules


WEAK_HINT_PREFIX = "fallback:"


def classify(title: str, hint: str | None = None, description: str | None = None) -> tuple[str, str, float]:
    """Returns (category, subcategory, confidence). A strong hint (source-provided genre / schema.org type) is checked
    first; a hint prefixed with ``fallback:`` (e.g. tourism-board listings) is only used when title/description match nothing."""
    weak_part = None
    if hint and WEAK_HINT_PREFIX in hint.lower():
        i = hint.lower().index(WEAK_HINT_PREFIX)
        weak_part, hint = hint[i + len(WEAK_HINT_PREFIX):].strip(), hint[:i].strip() or None
    weak = weak_part is not None
    texts = [] if not hint else [(f" {hint.lower()} ", 1.0)]
    texts.append((f" {(title or '').lower()} ", 0.9))
    if description:
        texts.append((f" {description.lower()[:500]} ", 0.6))
    if weak and weak_part:
        texts.append((f" {weak_part.lower()} ", 0.5))
    for text, conf in texts:
        for cat, sub, kws in _rules():
            for kw in kws:
                if kw in text:
                    return cat, sub, conf
    default = categories_config().get("default", {})
    return default.get("category", "other"), default.get("subcategory", "general"), 0.3


def category_factor(category: str) -> float:
    return float(categories_config().get("category_scores", {}).get(category, 0.3))
