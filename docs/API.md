# API Reference

Base: `/api` · Interactive docs: `/api/docs` · Envelope:
```json
{"success": true, "data": …, "meta": {"page": 1, "page_size": 50, "total": 100}}
{"success": false, "error": {"code": "EVENT_NOT_FOUND", "message": "Event not found"}}
```

| Method | Path | Description | Params |
|---|---|---|---|
| GET | /events | Event feed | range=today\|tomorrow\|7d\|30d, date_from, date_to, category, subcategory, city, region, demand=HIGH,VERY_HIGH, min_score, venue, status, source, q, **quality=HIGH,MEDIUM,LOW**, **confidence=OFFICIAL,TRUSTED,SECONDARY,UNVERIFIED,CURATED**, sort=score\|date\|updated\|quality, page, page_size (≤200) |
| GET | /events/{id} | Full detail incl. explicit `facts` (sourced) / `modelled` (estimates) / `recommendations` split, quality reasons, status_reason | |
| GET | /events/{id}/snapshots | Point-in-time snapshots written on create/change | limit |
| GET | /changes | Change log | days, change_type, page |
| GET | /opportunities | Taxi opportunities | demand, days, opportunity_type, city, page |
| GET | /opportunities/{id} | | |
| GET | /actions | Marketing actions | status (default open), days, priority, page |
| POST | /actions/{id}/complete · /dismiss · /start · /schedule {scheduled_for} | Action lifecycle | |
| GET | /dashboard/summary | KPI cards + top opportunities | |
| GET | /dashboard/map | Markers with lat/lon/score | days, min_score |
| GET | /dashboard/trends | Analytics aggregates | days |
| GET | /dashboard/calendar | Events overlapping a range | start, end |
| GET | /reports/daily | Daily report JSON (same content as Telegram digest) | |
| GET | /sources · /sources/{id}/health | Registry + live health check + recent runs | |
| POST | /sources/{id}/toggle 🔒 | Enable/disable | |
| GET | /venues · /cities · /regions · /categories | Reference data with upcoming counts | q, seeded_only |
| GET | /health · /health/detailed | Liveness · full system health | |
| GET | /settings · PUT /settings/{key} 🔒 | Non-secret runtime settings | |
| POST | /pipeline/run 🔒 | Trigger pipeline (background unless `sync=true`) | sources, notify, sync |
| GET | /pipeline/runs | Run history | limit |
| GET | /coverage | Configured Coverage Index, targets by status, horizons, gaps by category/city/region, source health | |
| GET | /coverage/sources | Source health incl. `SOURCE SILENT`, failure_rate, future_events | |
| GET | /data-quality | Quality levels, confidence mix, freshness, missing fields, possible duplicates | |
| GET | /sources/{id}/events | Source drilldown: linked events + recent runs | page, page_size |

Phase 2 fields on events: `source_confidence`, `event_quality_score`, `quality_level`, `quality_reasons`, `freshness_score`,
`last_verified_at`, `status_reason`, `source_count`, `event_subtype`. Opportunities carry `score_components` (v2 additive formula) and
`confidence`; actions carry `reason` and `recommended_date`. Actions auto-dismissed by the gate have status `DISMISSED_AUTO`.

🔒 = requires header `X-Admin-Token` when `API_ADMIN_TOKEN` is set (open in local dev when unset).

### GET /api/marketing-actions
Alias of `/api/actions` (same envelope). Filters: `action_type`, `city`, `status`, `q`, `sort` (`priority|date|created`), `page`, `page_size` (max 200).

### GET /api/events?missing=
`missing=time|venue|location|official_url|coordinates|capacity` returns events lacking that field (used by the Data Quality click-through). Also `quality=HIGH|MEDIUM|LOW`, `confidence=OFFICIAL|TRUSTED|COMMUNITY|UNVERIFIED`.

## Phase 3 additions

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health/detailed` | DB, last/recent runs, per-source status, notification + map + LLM + external-data providers, scheduler (next cron), recent errors |
| GET | `/api/sources/{id}` | Source detail: status, `disabled_reason` (e.g. `API key not configured (TICKETMASTER_API_KEY)`), non-secret config, last 30 runs |
| GET | `/api/marketing-actions/{id}` | Single action |
| POST | `/api/marketing-actions/actions/{id}/plan` · `/schedule` · `/start` · `/done` · `/dismiss` · `/reopen` | Status machine NEW → PLANNED → SCHEDULED → IN_PROGRESS → DONE / DISMISSED (reopen → NEW) |
| GET | `/api/calendar?start=&end=` | Alias of `/api/dashboard/calendar` |
| PUT | `/api/settings` (admin) | Bulk update of non-secret keys only (`service_area`, `home_city`, `priority_categories`, `score_thresholds`, `notifications`, `collection_frequency`). Secret keys → 400; secrets live in env only |
| GET | `/api/export/events` · `/opportunities` · `/marketing-actions` · `/reports` | `?format=csv|json`; events accept the same filters as `/api/events`; streamed, DB-side filtering |
| GET | `/api/bookings/status` | Historical bookings count, correlations, `model_mode` (`DETERMINISTIC` until ≥200 labelled events) |
| POST | `/api/bookings/import` (admin, multipart) | CSV / XLSX / JSON upload → canonical `taxi_bookings` |
| POST | `/api/bookings/correlate` (admin) | Spatial-temporal join events ↔ bookings → `event_booking_correlations` (distance_km, time_delta_min, match_confidence). Correlation ≠ causation |

`/api/dashboard/summary` now includes `next_scheduled_run` (06:00 UTC cron) and `data_freshness` (`hours_since_last_success`, `avg_freshness_score`, `label` FRESH ≤ 26 h / STALE / UNKNOWN).
