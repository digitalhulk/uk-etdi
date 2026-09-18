# Database

SQLite (WAL mode) by default; SQLAlchemy 2.x models are Postgres-compatible (JSON, Date, DateTime, FK cascades). Lightweight migration runner (`db/migrations/runner.py`, `schema_migrations` table); replace with Alembic when schema churn warrants.

## Tables (19)

`event_snapshots` (Phase 2): point-in-time copy of tracked facts written when a run creates or changes an event (`reason` NEW/CHANGED). Retention 180 days.

Phase 2 columns added by migration `0002_phase2_quality` (events: source_confidence, event_quality_score, quality_level, quality_reasons, freshness_score, last_verified_at, status_reason, source_count, event_subtype; opportunities: score_components, confidence; marketing_actions: recommended_date, reason). `0003_phase2_indexes` adds composite indexes (category+date, city+date, quality, last_seen, action status+priority, source_runs, raw fetched_at).
| Table | Purpose | Key columns |
|---|---|---|
| sources | Connector registry + live status | key, type, enabled, priority, status, last_success_at, last_error, last_response_ms |
| source_runs | Per-collector execution log | source_id, pipeline_run_id, status, events_collected, response_ms, error |
| raw_events | Immutable raw payloads | source_id, source_external_id, payload(JSON), source_url, fetched_at, hash — UNIQUE(source, ext, hash) |
| events | Canonical event master | canonical_event_id, fingerprint, title, normalized_title, category, subcategory, date_start/end, time_start/end, timezone, venue_id, city_id, region_id, postcode, lat/lon, organizer, official_url, ticket_url, status, attendance_estimate(+confidence), venue_capacity, recurrence, first/last_seen_at, last_updated_at, opportunity_score, demand_level, marketing_priority, score_breakdown(JSON), demand_windows(JSON), primary_source |
| event_sources | Many sources → one event | event_id, source_id, external_id, source_url, first_seen, last_seen, last_fetched — UNIQUE(source, external_id) |
| venues | Venue intelligence | name, normalized_name, aliases, city_id, postcode, lat/lon, capacity, capacity_source, venue_type, importance_score, airport/station_distance_km, is_seeded |
| cities | City registry | name, region_id, country, lat/lon, population(+source), priority, tourism, aliases |
| regions | UK regions/nations | name, country |
| categories / event_categories | Taxonomy + multi-label link | name, subcategory / event_id, category_id, confidence |
| event_changes | Change log | event_id, pipeline_run_id, change_type, field, old_value, new_value, detected_at |
| opportunities | Taxi opportunities | event_id, opportunity_type, score, demand_level, window_start/end, window_label, reasons(JSON), recommended_action — UNIQUE(event, type) |
| marketing_actions | Action tracker | event_id, action_type, priority, title, description, suggested_keyword/audience/channel, recommended_time, status, scheduled_for |
| notifications | Outbound log | channel, recipient, subject, body, status, error, sent_at |
| pipeline_runs | Run model | trigger, status, sources_*, events_raw/valid/created/updated, duplicates_removed, changes_detected, opportunities/actions_generated, notifications_sent, errors, duration_seconds, stages(JSON) |
| system_health | Component snapshots | component, status, details |
| errors | Error audit | component, message, details, pipeline_run_id |
| settings | Runtime settings (non-secret) | key, value(JSON) |

## Indexes
events(date_start), events(opportunity_score), events(city_id), events(fingerprint), events(normalized_title), raw_events(hash), event_changes(detected_at), plus FK indexes.

## Retention (pipeline `retention` stage)
Raw payloads 30 d · snapshots 180 d · system_health/errors 60 d · pipeline runs 365 d (env `RETENTION_*_DAYS`). Canonical events are **never** deleted; past events are marked COMPLETED. Stale `RUNNING` runs older than 3 h are marked ABORTED by the next run.

## Data policy
`events.description` holds ≤300 chars of factual metadata (e.g. "Premier League round 7"), never copied marketing copy. `raw_events.payload` stores only the fields the connector selected (ids, names, dates, venue, URL).

## Switching to PostgreSQL
`pip install psycopg[binary]`, set `DATABASE_URL=postgresql+psycopg://user:pass@host/db`, run `scripts/migrate.py`. No code changes.

### event_snapshots.snapshot_hash (Phase 2, migration 0004)
sha256 of the tracked fact set (title, dates, times, venue, status, urls). A new snapshot row is written only when the hash differs from the latest one for that event, so unchanged runs add nothing.
