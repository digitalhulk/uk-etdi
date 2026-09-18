# Architecture

Modular monolith: one FastAPI process, clear module boundaries so any stage can be extracted later.

```
config/*.yaml ─┐
               ▼
 collectors/ (registry → Collector.run()) ── CollectResult(NormalizedEvent[])
               ▼
 processors/  validation → normalize → classify → deduplicate → change_detection
               ▼
 intelligence/ geography → venue_score → demand_score → taxi_opportunity → marketing
               ▼
 db/ (SQLAlchemy models, migrations runner, seed)  ──►  api/ (FastAPI routes + serializers)
               ▼                                             ▼
 orchestration/ pipeline.py (17 stages) · jobs · scheduler   frontend/ (hash-router SPA)
               ▼
 notifications/ telegram · email · sheets
```

## Pipeline stages (`orchestration/pipeline.py`)
1. load_configuration (reload YAML, seed reference data)
2. collect (each collector: timeout, 3 retries w/ backoff, independent failure, SourceRun row)
3. validate_raw / store raw payloads (`raw_events`, hash-deduped, never overwritten)
4. normalize_validate (date sanity, location presence)
5. classify → geo → dedupe → persist (single transaction per run)
6. change detection (per field, vs previous snapshot)
7. intelligence (score, windows, opportunities, marketing actions — upserted, user statuses preserved)
8. report + sync outputs (Sheets optional)
9. notify (Telegram; SKIPPED when unconfigured)
10. record health (`system_health`)

Every stage is timed and recorded in `pipeline_runs.stages`; failures are logged to `errors` and the run is marked PARTIAL.

## Phase 2 additions
* `core/netsafe.py` SSRF policy; `core/service_area.py` (Settings table → env fallback); `core/logging.py` JSON logs (`LOG_FORMAT=json`).
* `collectors/base.py` `safe_fetch` + `CollectResult` counters (endpoints_attempted/ok, blocked) → status HEALTHY/DEGRADED/FAILED/EMPTY/DISABLED derived automatically.
* `collectors/venue.py`, `institutions.py`, `council.py` registry-driven; `intelligence/quality.py` (quality, freshness, status engine);
  `intelligence/coverage.py` (Configured Coverage Index, data quality); opportunity v2 in `taxi_opportunity.py` (additive `score_components`);
  action gating in `marketing.py`; pipeline stages `quality_freshness_status` and `retention`; stale-run recovery.

## Idempotency
Match order: (source, external_id) → exact fingerprint (`sha256(normalized_title|date|venue|city)`) → fuzzy (same date, 0.6·title + 0.25·venue + 0.15·city ≥ 0.88).
Unique constraints: `event_sources(source_id, external_id)`, `raw_events(source, ext, hash)`, `opportunities(event, type)`, `marketing_actions(event, type)`.

## Source priority & conflict resolution
`sources.yaml.priority` decides which source's title/date/time/status wins for a canonical event; lower-priority sources still fill gaps (time_start etc.).

## Timezones
All UTC feed timestamps → `Europe/London` via `zoneinfo` (BST/GMT correct, tested). Events store local date + `HH:MM`.

## Scoring model
`score = Σ component_factor(0..1) × weight` with weights from `scoring.yaml` (sum 100).
Components: event_scale (modelled attendance band), venue_scale (capacity band + importance), timing (evening/late/weekend), location (city priority + service area), transport (station/airport distance), category, tourism, duration. Cancelled/postponed ⇒ 0.

## Provider abstraction points
| Concern | Default | Swap |
|---|---|---|
| Database | SQLite | `DATABASE_URL=postgresql+psycopg://…` |
| Scheduler | GitHub Actions cron | `SCHEDULER_ENABLED=1` in-process, or any cron calling `scripts/run_pipeline.py` / `POST /api/pipeline/run` |
| Map tiles | OpenStreetMap (keyless) | `window.UK_ETDI_TILES` |
| Notifications | Telegram | `notifications/email.py`, add Slack similarly |
| Postcode geocoding | off | `GeographyEngine(use_postcode_api=True)` (postcodes.io, free) |
| Sheets | webhook (Apps Script) | any HTTP sink |

## Path to microservices (if ever needed)
Collectors → queue workers; intelligence → stateless scorer; API/dashboard → read replicas. Interfaces (`NormalizedEvent`, `ScoreResult`, repositories) already isolate these.
