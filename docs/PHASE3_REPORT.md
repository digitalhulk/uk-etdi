# Phase 3 — Final completion & production launch report

Measured on **18 Sep 2026** (sandbox), pipeline runs #25–#40. Every number below is read from `data/uk_etdi.db` or a live API call
— nothing is estimated. Configured/Observed coverage only; this is **not** "all UK events".

## 1. Live state (run #40)

| Metric | Phase 2 end (run #24) | Phase 3 end (run #40) |
|---|---|---|
| Future canonical events | 1,667 | **2,920** |
| Horizons today / 7d / 30d / 90d | 12 / 85 / 320 / 835 | **15 / 125 / 494 / 1,338** |
| Categories (top level) | football 1,154 · community 133 · horse racing 119 · concert 99 · rugby 92 · theatre 5 | **sports 1,407** (football 1,188, horse racing 119, rugby 92, ice hockey 6) · **theatre 1,097** · community 206 · music 105 · education 46 · festival 26 · arts 16 · comedy 9 |
| Sources HEALTHY / EMPTY / DISABLED | 4 / 6 / 3 | **5 / 5 / 3** (universities now HEALTHY) |
| Per-source future events | fixtures 1,246 · venue pages 247 · tourism 178 | fixtures 1,277 · **venue pages 1,345** · tourism 256 · **universities 41** · curated 1 |
| Quality HIGH / MEDIUM / LOW | 391 / 1,273 / 3 | **1,582 / 1,336 / 2** |
| Confidence OFFICIAL / TRUSTED / UNVERIFIED | 246 / 1,419 / 4 | **1,386 / 1,532 / 2** |
| Regions with events | 11 (NI = 0) | **12 (NI = 3)** |
| Cities / venues with events | 60 / 123 | **62 / 163** |
| Configured Coverage Index | 63 | **72** |
| Opportunities (10 types, stored separately) | 11,072 | 17,992 |
| Marketing actions NEW / DISMISSED / DISMISSED_AUTO | 745 / 21 / 7,554 | 746 / 21 / 7,562 (gate keeps volume flat) |
| Tests | 44 passed, 1 skipped | **86 passed, 2 skipped** (`backend/tests`, 7 files) |
| Consecutive runs 0 created / 0 updated / 0 dupes / 0 changes | 2 | **4 — runs 38, 39, 40, 41**, zero rows in `event_changes` |
| Run duration | 2–3 min | 3.7–5 min (13 sources, ≥0.6 s/host politeness, Oxfordshire Crawl-delay 3 s) |

Dashboard: `http://<host>:8000` — Overview shows last run, **next scheduled run (06:00 UTC)** and **data freshness (FRESH/STALE)**; System page shows API, scheduler, map provider (OSM tiles / offline SVG), notification providers, LLM (NullLLM — deterministic), external data, historical bookings (`DETERMINISTIC`, 0/200 labelled).

## 2. What Phase 3 delivered (by section)

* **§6 provider abstractions** — `backend/app/providers/`: `EventSource` (existing collectors), `MapProvider` (OSM / Offline), `NotificationProvider` (Telegram / Email / Console), `StorageProvider` (local), `LLMProvider` (NullLLM, optional), `ExternalDataProvider` (postcodes.io geocoding). Registry-driven; `/api/health/detailed` lists all with configured flags. No secrets returned anywhere.
* **§10–12** Ticketmaster / Eventbrite / JamBase connectors complete; **DISABLED with reason `API key not configured (…)`** from the first run (fixed a UNKNOWN-before-first-run bug found by a test).
* **§13–16 coverage** — Nimax West End (per-performance JSON-LD), Spektrix RSS theatres (Edinburgh, Dundee, Birmingham, Oxford), UEFA Nations League / Europa / Conference / Scottish Premiership (UK venues only → Scotland, Wales, NI internationals), Visit Leicester, Aberdeen RSS + Cambridge talks ICS. Cricket: no key-less structured domestic feed exists (ECB/county sites JS-only or 403) — documented, not faked.
* **§17–20** institutions/councils engines are registry-only; schools/colleges remain EMPTY (no public calendars registered) — by design.
* **§22–25 identity & change detection** — three real idempotency root causes fixed (see `docs/OPERATIONS.md` §Idempotency): same-source repeat sessions vs cross-source time discrepancies; stale `external_id` link re-pointing; placeholder "To be announced v To be announced" fixtures rejected. Nothing was suppressed.
* **§29–30** ten opportunity types stored separately; demand windows labelled *Modelled demand window* everywhere (API, digest, UI).
* **§31–33 historical bookings** — `taxi_bookings`, `event_booking_correlations`, `demand_feature_rows`; CSV/XLSX/JSON/API/DB readers; `config/bookings.yaml` column map; CLI + admin API; correlation is spatial-temporal only and labelled as such; model stays DETERMINISTIC until ≥200 labelled events. **No ML accuracy is claimed.**
* **§34–36** eight channels incl. EMAIL/PARTNERSHIP; status machine NEW → PLANNED → SCHEDULED → IN_PROGRESS → DONE / DISMISSED (+ reopen), buttons in the Actions page.
* **§37–51 dashboard** — Overview KPIs incl. next run & freshness; Actions tabs per status; System page providers; Sources show `disabled_reason`.
* **§52–53 API** — added `/api/sources/{id}`, `/api/marketing-actions/{id}`, `/api/calendar`, `PUT /api/settings` (non-secret keys only; secrets → 400), `/api/export/*` CSV/JSON (streamed, DB-side filters), `/api/bookings/*`, `/api/health/detailed`.
* **§54 CLI** — `health, sources, coverage, collect, pipeline --dry-run, report [--send], events, bookings import|correlate|status`.
* **§55–57** GitHub Actions daily 06:00 UTC + tests workflow; Telegram digest verified in dry-run: header, VERY HIGH/HIGH/MEDIUM counts, TOP 5 with capacity provenance + *departures (modelled)* + recommended action, EVENT CHANGES, category counts, SYSTEM block, MODELLED disclaimer; no-opportunity fallback message.
* **§59–61** exports; SSRF guard (`netsafe.validate_url`) and admin token tested.
* **§62 tests** — 85 meaningful tests: provider registry, collector parsers with fixed payloads (fixtures BST split, ICS, Spektrix RSS, JSON-LD strict=False), validation horizons + non-event titles, classifier precedence (title beats `fallback:` venue hint; ice hockey before generic " v "), session-split thresholds, URL-upgrade rule, bookings ingest idempotency + match confidence, all four exports CSV+JSON, action transitions, settings secrecy, SSRF, admin auth, CLI exit codes.
* **§63–65** four consecutive clean runs (38–41). **§64 per-source regression**: a source whose count drops >50 % against its last successful run (or to zero) is logged as `regression:` in `errors`, appended to its `source_runs.error`, and printed in the digest SYSTEM block — zero is never reported as success. Sources whose endpoints are all 401/403/406/robots now get status **BLOCKED** (shown on Sources/Coverage pages and in the digest) and are never retried aggressively. Real runs only — no synthetic data at any stage.

## 3. Findings fixed during the real runs (evidence-driven)

| Symptom | Root cause | Fix |
|---|---|---|
| 2 TIME_CHANGED per run flip-flopping 10:30↔12:00 (Dundee Rep "Doors Open Day") | Two RSS items (two tours) for one title/day, gap 90 min < 120 min session threshold → merged, then the link for the second item kept re-timing the first | Same-source distinct start time = separate session; a link that resolves to an existing sibling session is re-pointed |
| 5–7 "duplicates removed" every run | Stale `event_sources` links left on the wrong session after a split | Re-point link when the resolved event changes |
| "Manchester Storm vs …", "Baby & Toddler Show", "Laver Cup Practice" classified *music* | Arena `category_hint: concerts` was a strong hint overriding titles | Arena hints made `fallback:`; ice-hockey and family keyword rules added to `config/categories.yaml` |
| "To be announced v To be announced" events (Premiership Rugby 2027 placeholders) | Feed placeholder rows passed validation | Added to `non_event_title_patterns`; rows removed |
| API sources showed UNKNOWN before the first run | Serializer used DB status only | Key-gated sources are DISABLED from creation |

## 4. Known limits (honest)

* Coverage is of the configured registry (CCI 72). 13 configured cities still have 0 events (list in `docs/SOURCE_COVERAGE.md`); NI has 3 (internationals only) — every NI venue site probed is JS-rendered or refuses automated clients.
* Cricket, national festivals, nightlife and most councils/universities have no key-less structured feeds; adding a Ticketmaster key (free tier) is the single biggest coverage lever and is a one-line env change.
* Demand, windows and scores are MODELLED (config-weighted, reasoned) — they are not observed demand and remain so until historical bookings are ingested.
* Run time grew to ~4 min because of per-performance detail fetches with politeness delays; still far inside the GitHub Actions free budget.

## 5. Launch checklist

1. `cp .env.example .env` → set `API_ADMIN_TOKEN`; optionally `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, `TICKETMASTER_API_KEY`.
2. `cd backend && pip install -r requirements.txt && python -m pytest -q` (85 passed).
3. `python -m app.cli pipeline` → `python -m app.cli health`.
4. `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` (or the GitHub Actions workflow for the daily 06:00 UTC run + digest).
5. Optional: `python -m app.cli bookings import bookings.csv && python -m app.cli bookings correlate`.
