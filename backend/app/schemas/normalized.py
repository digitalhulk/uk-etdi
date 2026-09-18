"""Canonical intermediate event shape produced by every collector's normalize()."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, field_validator, Field


class NormalizedEvent(BaseModel):
    source_key: str
    external_id: str
    title: str
    description: str | None = None
    category_hint: str | None = None
    date_start: date
    date_end: date | None = None
    time_start: str | None = None  # "HH:MM" Europe/London
    time_end: str | None = None
    venue_name: str | None = None
    city_name: str | None = None
    postcode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    organizer: str | None = None
    official_url: str | None = None
    ticket_url: str | None = None

    @field_validator("official_url", "ticket_url", "source_url", mode="before", check_fields=False)
    @classmethod
    def _strip_url(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v
    source_url: str | None = None
    status: str = "SCHEDULED"  # SCHEDULED / CONFIRMED / CANCELLED / POSTPONED / RESCHEDULED / SOLD_OUT / UNKNOWN
    source_confidence: str | None = None  # OFFICIAL / TRUSTED / SECONDARY / UNVERIFIED (filled by collector)
    event_subtype: str | None = None  # schema.org @type e.g. MusicEvent
    sold_out: bool = False
    venue_capacity: int | None = None
    recurrence: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
