"""Lightweight, dependency-free migration runner (Alembic can replace this later).
Each migration is (version, sql_statements). Applied versions are tracked in schema_migrations."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

MIGRATIONS: list[tuple[str, list[str]]] = [
    ("0001_indexes", [
        "CREATE INDEX IF NOT EXISTS ix_events_date_start ON events(date_start)",
        "CREATE INDEX IF NOT EXISTS ix_events_score ON events(opportunity_score)",
        "CREATE INDEX IF NOT EXISTS ix_events_city ON events(city_id)",
        "CREATE INDEX IF NOT EXISTS ix_events_fingerprint ON events(fingerprint)",
        "CREATE INDEX IF NOT EXISTS ix_raw_events_hash ON raw_events(hash)",
        "CREATE INDEX IF NOT EXISTS ix_event_changes_detected ON event_changes(detected_at)",
    ]),
    ("0002_phase2_quality", [
        "ALTER TABLE events ADD COLUMN source_confidence VARCHAR(20)",
        "ALTER TABLE events ADD COLUMN event_quality_score INTEGER",
        "ALTER TABLE events ADD COLUMN quality_level VARCHAR(10)",
        "ALTER TABLE events ADD COLUMN quality_reasons JSON",
        "ALTER TABLE events ADD COLUMN freshness_score INTEGER",
        "ALTER TABLE events ADD COLUMN last_verified_at DATETIME",
        "ALTER TABLE events ADD COLUMN status_reason VARCHAR(200)",
        "ALTER TABLE events ADD COLUMN source_count INTEGER DEFAULT 1",
        "ALTER TABLE events ADD COLUMN event_subtype VARCHAR(40)",
        "ALTER TABLE opportunities ADD COLUMN score_components JSON",
        "ALTER TABLE opportunities ADD COLUMN confidence VARCHAR(10)",
        "ALTER TABLE marketing_actions ADD COLUMN recommended_date VARCHAR(10)",
        "ALTER TABLE marketing_actions ADD COLUMN reason TEXT",
    ]),
    ("0004_snapshot_hash", [
        "ALTER TABLE event_snapshots ADD COLUMN snapshot_hash VARCHAR(64)",
        "CREATE INDEX IF NOT EXISTS ix_event_snapshots_hash ON event_snapshots(snapshot_hash)",
    ]),
    ("0005_bookings_indexes", [
        "CREATE INDEX IF NOT EXISTS ix_taxi_bookings_pickup_dt ON taxi_bookings(pickup_datetime)",
        "CREATE INDEX IF NOT EXISTS ix_ebc_event ON event_booking_correlations(event_id)",
    ]),
    ("0003_phase2_indexes", [
        "CREATE INDEX IF NOT EXISTS ix_events_quality ON events(quality_level)",
        "CREATE INDEX IF NOT EXISTS ix_events_category_date ON events(category, date_start)",
        "CREATE INDEX IF NOT EXISTS ix_events_city_date ON events(city_id, date_start)",
        "CREATE INDEX IF NOT EXISTS ix_events_last_seen ON events(last_seen_at)",
        "CREATE INDEX IF NOT EXISTS ix_event_sources_event ON event_sources(event_id)",
        "CREATE INDEX IF NOT EXISTS ix_opportunities_score ON opportunities(score)",
        "CREATE INDEX IF NOT EXISTS ix_actions_status_priority ON marketing_actions(status, priority)",
        "CREATE INDEX IF NOT EXISTS ix_source_runs_source_started ON source_runs(source_id, started_at)",
        "CREATE INDEX IF NOT EXISTS ix_raw_events_fetched ON raw_events(fetched_at)",
    ]),
]


def run_migrations(engine: Engine) -> list[str]:
    applied: list[str] = []
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"))
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations")).fetchall()}
        for version, statements in MIGRATIONS:
            if version in done:
                continue
            for stmt in statements:
                try:
                    conn.execute(text(stmt))
                except Exception as exc:  # fresh DBs: create_all already created the column → skip
                    if "duplicate column" in str(exc).lower() or "already exists" in str(exc).lower():
                        continue
                    raise
            conn.execute(text("INSERT INTO schema_migrations(version) VALUES (:v)"), {"v": version})
            applied.append(version)
    return applied
