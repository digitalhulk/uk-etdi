"""SQLAlchemy ORM models — all 18 tables of the UK-ETDI schema."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Region(Base, TimestampMixin):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    country: Mapped[str] = mapped_column(String(60), nullable=False, default="England")


class City(Base, TimestampMixin):
    __tablename__ = "cities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    country: Mapped[str] = mapped_column(String(60), default="England")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    population: Mapped[int | None] = mapped_column(Integer)
    population_source: Mapped[str | None] = mapped_column(String(200))
    priority: Mapped[int] = mapped_column(Integer, default=50)
    tourism: Mapped[float] = mapped_column(Float, default=0.3)
    aliases: Mapped[list | None] = mapped_column(JSON)
    region: Mapped[Region | None] = relationship()


class Venue(Base, TimestampMixin):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    aliases: Mapped[list | None] = mapped_column(JSON)
    address: Mapped[str | None] = mapped_column(String(300))
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"))
    postcode: Mapped[str | None] = mapped_column(String(12))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    capacity: Mapped[int | None] = mapped_column(Integer)
    capacity_source: Mapped[str | None] = mapped_column(String(200))
    venue_type: Mapped[str | None] = mapped_column(String(40))
    importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    airport_distance_km: Mapped[float | None] = mapped_column(Float)
    station_distance_km: Mapped[float | None] = mapped_column(Float)
    is_seeded: Mapped[bool] = mapped_column(Boolean, default=False)
    city: Mapped[City | None] = relationship()


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(60))
    __table_args__ = (UniqueConstraint("name", "subcategory", name="uq_category"),)


class Source(Base, TimestampMixin):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")  # HEALTHY / DEGRADED / FAILED / DISABLED
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_response_ms: Mapped[int | None] = mapped_column(Integer)
    last_events_collected: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict | None] = mapped_column(JSON)


class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    events_collected: Mapped[int] = mapped_column(Integer, default=0)
    response_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class RawEvent(Base):
    __tablename__ = "raw_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    source_external_id: Mapped[str] = mapped_column(String(200), index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(600))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    __table_args__ = (UniqueConstraint("source_id", "source_external_id", "hash", name="uq_raw_source_ext_hash"),)


class Event(Base, TimestampMixin):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_event_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)  # short factual summary only
    category: Mapped[str] = mapped_column(String(60), default="other", index=True)
    subcategory: Mapped[str | None] = mapped_column(String(60))
    date_start: Mapped[datetime] = mapped_column(Date, nullable=False)
    date_end: Mapped[datetime | None] = mapped_column(Date)
    time_start: Mapped[str | None] = mapped_column(String(5))  # HH:MM local
    time_end: Mapped[str | None] = mapped_column(String(5))
    timezone: Mapped[str] = mapped_column(String(40), default="Europe/London")
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), index=True)
    venue_name_raw: Mapped[str | None] = mapped_column(String(200))
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"))
    city_name_raw: Mapped[str | None] = mapped_column(String(120))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    postcode: Mapped[str | None] = mapped_column(String(12))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    organizer: Mapped[str | None] = mapped_column(String(200))
    official_url: Mapped[str | None] = mapped_column(String(600))
    ticket_url: Mapped[str | None] = mapped_column(String(600))
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED", index=True)
    attendance_estimate: Mapped[int | None] = mapped_column(Integer)
    attendance_confidence: Mapped[str | None] = mapped_column(String(20))  # LOW / MEDIUM / HIGH (modelled)
    venue_capacity: Mapped[int | None] = mapped_column(Integer)
    recurrence: Mapped[str | None] = mapped_column(String(40))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    opportunity_score: Mapped[int] = mapped_column(Integer, default=0)
    demand_level: Mapped[str] = mapped_column(String(20), default="LOW")
    marketing_priority: Mapped[str | None] = mapped_column(String(5))
    score_breakdown: Mapped[dict | None] = mapped_column(JSON)
    demand_windows: Mapped[dict | None] = mapped_column(JSON)
    primary_source: Mapped[str | None] = mapped_column(String(60))
    # ---- Phase 2 quality / trust / freshness ----
    source_confidence: Mapped[str | None] = mapped_column(String(20))   # OFFICIAL / TRUSTED / SECONDARY / UNVERIFIED
    event_quality_score: Mapped[int | None] = mapped_column(Integer)      # 0..100
    quality_level: Mapped[str | None] = mapped_column(String(10))         # HIGH / MEDIUM / LOW
    quality_reasons: Mapped[list | None] = mapped_column(JSON)
    freshness_score: Mapped[int | None] = mapped_column(Integer)          # 0..100 (decays with time since last verification)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)   # last time any source returned this event
    status_reason: Mapped[str | None] = mapped_column(String(200))
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    event_subtype: Mapped[str | None] = mapped_column(String(40))

    venue: Mapped[Venue | None] = relationship()
    city: Mapped[City | None] = relationship()
    region: Mapped[Region | None] = relationship()
    sources: Mapped[list["EventSource"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    changes: Mapped[list["EventChange"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    marketing_actions: Mapped[list["MarketingAction"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventCategory(Base):
    __tablename__ = "event_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    __table_args__ = (UniqueConstraint("event_id", "category_id", name="uq_event_category"),)


class EventSource(Base):
    __tablename__ = "event_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(600))
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_fetched: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    event: Mapped[Event] = relationship(back_populates="sources")
    source: Mapped[Source] = relationship()
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_external"),)


class EventChange(Base):
    __tablename__ = "event_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    change_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    field: Mapped[str | None] = mapped_column(String(60))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    event: Mapped[Event] = relationship(back_populates="changes")


class EventSnapshot(Base):
    """Point-in-time copy of the tracked event facts, written when a pipeline run creates or changes an event."""
    __tablename__ = "event_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    taken_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    reason: Mapped[str] = mapped_column(String(30), default="CHANGED")  # NEW / CHANGED / STATUS
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    opportunity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    demand_level: Mapped[str] = mapped_column(String(20), default="LOW")
    window_start: Mapped[str | None] = mapped_column(String(5))
    window_end: Mapped[str | None] = mapped_column(String(5))
    window_label: Mapped[str] = mapped_column(String(60), default="Modelled demand window")
    reasons: Mapped[list | None] = mapped_column(JSON)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    score_components: Mapped[dict | None] = mapped_column(JSON)  # v2: transparent additive components + gate
    confidence: Mapped[str | None] = mapped_column(String(10))    # HIGH / MEDIUM / LOW (from event quality)
    event: Mapped[Event] = relationship(back_populates="opportunities")
    __table_args__ = (UniqueConstraint("event_id", "opportunity_type", name="uq_event_opportunity"),)


class MarketingAction(Base):
    __tablename__ = "marketing_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[str] = mapped_column(String(5), default="P3")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    suggested_keyword: Mapped[str | None] = mapped_column(String(200))
    suggested_audience: Mapped[str | None] = mapped_column(String(200))
    suggested_channel: Mapped[str | None] = mapped_column(String(60))
    recommended_time: Mapped[str | None] = mapped_column(String(60))
    recommended_date: Mapped[str | None] = mapped_column(String(10))  # ISO date the action should go live
    reason: Mapped[str | None] = mapped_column(Text)                  # why this action was generated (gating facts)
    status: Mapped[str] = mapped_column(String(20), default="NEW", index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    event: Mapped[Event] = relationship(back_populates="marketing_actions")
    __table_args__ = (UniqueConstraint("event_id", "action_type", name="uq_event_action"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(120))
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    error: Mapped[str | None] = mapped_column(Text)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    sources_attempted: Mapped[int] = mapped_column(Integer, default=0)
    sources_successful: Mapped[int] = mapped_column(Integer, default=0)
    sources_failed: Mapped[int] = mapped_column(Integer, default=0)
    events_raw: Mapped[int] = mapped_column(Integer, default=0)
    events_valid: Mapped[int] = mapped_column(Integer, default=0)
    events_created: Mapped[int] = mapped_column(Integer, default=0)
    events_updated: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_removed: Mapped[int] = mapped_column(Integer, default=0)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0)
    opportunities_generated: Mapped[int] = mapped_column(Integer, default=0)
    actions_generated: Mapped[int] = mapped_column(Integer, default=0)
    notifications_sent: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    stages: Mapped[dict | None] = mapped_column(JSON)


class SystemHealth(Base):
    __tablename__ = "system_health"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    component: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)


class ErrorLog(Base):
    __tablename__ = "errors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    component: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


__all__ = [
    "Region", "City", "Venue", "Category", "Source", "SourceRun", "RawEvent", "Event", "EventCategory",
    "EventSource", "EventChange", "Opportunity", "MarketingAction", "Notification", "PipelineRun",
    "SystemHealth", "ErrorLog", "Setting", "utcnow",
]


# ---------------------------------------------------------------------------------------------------------------------
# Historical taxi data architecture (section 31–33). Optional: the platform runs without any rows in these tables.
# ---------------------------------------------------------------------------------------------------------------------
class TaxiBooking(Base):
    """Canonical booking schema. Ingested from CSV / XLSX / JSON / API / DB connector via app.bookings.ingest."""
    __tablename__ = "taxi_bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    booking_created_at: Mapped[datetime | None] = mapped_column(DateTime)
    pickup_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    dropoff_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    pickup_postcode: Mapped[str | None] = mapped_column(String(10), index=True)
    dropoff_postcode: Mapped[str | None] = mapped_column(String(10), index=True)
    pickup_lat: Mapped[float | None] = mapped_column(Float)
    pickup_lon: Mapped[float | None] = mapped_column(Float)
    dropoff_lat: Mapped[float | None] = mapped_column(Float)
    dropoff_lon: Mapped[float | None] = mapped_column(Float)
    fare: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(20))
    vehicle_type: Mapped[str | None] = mapped_column(String(30))
    source_file: Mapped[str | None] = mapped_column(String(200))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EventBookingCorrelation(Base):
    """A booking that plausibly relates to an event (geography + time). Correlation ≠ causation — see match_confidence."""
    __tablename__ = "event_booking_correlations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("taxi_bookings.id", ondelete="CASCADE"), index=True)
    leg: Mapped[str] = mapped_column(String(10), default="DROPOFF")  # PICKUP (venue→away) | DROPOFF (→venue)
    distance_km: Mapped[float] = mapped_column(Float)
    time_delta_min: Mapped[int] = mapped_column(Integer)  # minutes relative to event start (negative = before)
    match_confidence: Mapped[float] = mapped_column(Float)  # 0..1
    method: Mapped[str] = mapped_column(String(40), default="geo_time_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("event_id", "booking_id", "leg", name="uq_event_booking_leg"),)


class DemandFeatureRow(Base):
    """Feature-store row per event (deterministic features now; label = correlated bookings when data exists)."""
    __tablename__ = "demand_features"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, unique=True)
    features: Mapped[dict] = mapped_column(JSON, nullable=False)
    label_bookings: Mapped[int | None] = mapped_column(Integer)  # observed correlated bookings; None until data exists
    model_mode: Mapped[str] = mapped_column(String(20), default="DETERMINISTIC")  # DETERMINISTIC | FORECAST
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
