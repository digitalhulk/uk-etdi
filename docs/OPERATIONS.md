# Operations Runbook

## Daily
* 07:00 local: Telegram digest arrives. No digest ⇒ check Actions run → `/api/health/detailed`.
* Review **Home → What to do today**; mark actions Done/Dismissed/Scheduled.
* Check **Changes** for CANCELLED / DATE_CHANGED on high-score events.

## Weekly
* **Sources** page: any FAILED source → open "Check" for the live health message. 403/401 ⇒ key expired or site policy changed; disable and open an issue.
* Review unmatched venues (`/api/venues?seeded_only=false` with `capacity=null`) → add to `config/venues.yaml` with a sourced capacity.
* Tune `config/scoring.yaml` if levels feel mis-calibrated; re-score without re-collecting: `python -c "from app.orchestration.jobs import job_rescore; job_rescore()"`.

## Pipeline statuses
SUCCESS (no stage errors) · PARTIAL (some errors but events processed) · FAILED (no valid events + errors). Source statuses: HEALTHY / DEGRADED (warnings) / FAILED / DISABLED (no key or toggled off).

## Common issues
| Symptom | Cause | Fix |
|---|---|---|
| Events "no city" | venue not in registry and no coordinates | add venue/alias to venues.yaml |
| Score 0 on a real event | status CANCELLED/POSTPONED from source | verify on official URL; source may lag |
| Duplicate events | title variation below 0.88 fuzzy threshold across sources | add alias to venue, or lower `AUTO_MERGE_THRESHOLD` cautiously |
| Telegram SKIPPED | token/chat id unset | set env vars |
| Windows unavailable | start time TBC | populated automatically once source publishes time |

## Data hygiene
`raw_events` grows with every payload change; prune >90 days if the SQLite file exceeds ~200 MB (`DELETE FROM raw_events WHERE fetched_at < date('now','-90 days')`).

## Manual controls
`POST /api/pipeline/run?sources=football_fixtures&notify=false` · dashboard "Run pipeline now" button · `scripts/send_digest.py` to resend the digest.

## CLI (Phase 2)
```
cd backend
python -m app.cli health                     # DB + last run + per-source status
python -m app.cli sources                    # registry → collector class / confidence
python -m app.cli coverage                   # Configured Coverage Index + gaps (JSON)
python -m app.cli collect --source venue_pages --show 10      # collect only, nothing persisted
python -m app.cli collect --city Oxford --category community
python -m app.cli pipeline --dry-run         # collect + validate, report what would persist
python -m app.cli pipeline --no-notify
```

## Source statuses (Phase 2)
`EMPTY` = reachable but 0 events (or nothing configured) — not an error. `SOURCE SILENT` = a previously active source has had no
success for >3 days; events keep their last state (`status_reason` = "SOURCE SILENT…") — absence is never treated as cancellation.
`BLOCKED` (403/406/robots) sources are recorded in `CollectResult.blocked` and not retried within the run; fix the config, don't hammer.

## Action volume
`config/scoring.yaml → action_gating` controls recommendations: min score 65, quality ≥ MEDIUM, inside service area, ≤30 days ahead,
≤8 per event, ≤400 new per run. Events that fall out of the gate get their untouched NEW actions moved to `DISMISSED_AUTO`.
Service area comes from Settings (`service_area_cities`) with env fallback — no user-specific area is hardcoded.

## CLI (Phase 3 — full set)

```bash
python -m app.cli health                          # DB + last run + per-source status
python -m app.cli sources                         # registry → collector class / confidence / DISABLED reason
python -m app.cli coverage [--json]               # Configured Coverage Index, horizons, gaps
python -m app.cli collect --source venue_pages [--city Leeds] [--category sports] [--show 10]   # nothing persisted
python -m app.cli pipeline [--dry-run] [--no-notify]
python -m app.cli report [--send] [--json]        # daily digest text (send = Telegram/email if configured)
python -m app.cli events [--days 7] [--city X] [--category sports] [--min-score 60] [--limit 50] [--json]
python -m app.cli bookings import FILE            # CSV / XLSX / JSON → taxi_bookings (idempotent on booking_id)
python -m app.cli bookings correlate              # events ↔ bookings spatial-temporal correlation
python -m app.cli bookings status                 # counts + model_mode (DETERMINISTIC until ≥200 labelled events)
```

## Historical bookings (optional, §31–33)

* Column mapping lives in `config/bookings.yaml` (`column_map`, `radius_km`, `time_window_min`, `min_labelled_events`).
* Canonical schema: `booking_id, booking_created_at, pickup_datetime, dropoff_datetime, pickup_postcode, dropoff_postcode, pickup_lat/lon, dropoff_lat/lon, fare, status, vehicle_type` — any missing column is simply null.
* Correlation writes `event_booking_correlations(event_id, booking_id, distance_km, time_delta_min, match_confidence)`. It is a spatial-temporal join **only**; it is never presented as causation, and the demand model stays `DETERMINISTIC`/MODELLED until the labelled threshold is reached. No ML accuracy is claimed anywhere.

## Idempotency verification (§63)

Run `python -m app.cli pipeline --no-notify` three times back-to-back and check `pipeline_runs`: `events_created = events_updated = duplicates_removed = changes_detected = 0` on runs 2 and 3 (a genuine new listing on a source between runs shows as exactly 1 NEW — inspect `event_changes` to confirm it is real, never suppress it).

Root causes fixed during Phase 3 (do not regress):
1. Same-source, same-title, same-day events with different start times are separate sessions (matinee/evening, hourly tours); across sources a <120 min discrepancy is a TIME_CHANGED, not a new event.
2. A source `external_id` link that resolves to another session is re-pointed to that session instead of flip-flopping the original event's time each run.
3. Placeholder fixtures (`To be announced v To be announced`) are rejected by `non_event_title_patterns`.
