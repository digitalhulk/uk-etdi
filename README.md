# 🚕 UK-ETDI — UK Event → Taxi Demand Intelligence Platform

Discovers public UK events, normalises + deduplicates them, scores their likely taxi demand with fully explained
0–100 scores, generates typed taxi opportunities and concrete marketing actions, and presents everything in an
operational dashboard — at **£0 recurring infrastructure cost**.

```
PUBLIC EVENT DATA → EVENT INTELLIGENCE → DEMAND SIGNAL → TAXI OPPORTUNITY → MARKETING OPPORTUNITY → ACTION
```

## Quick start (2 minutes)

```bash
git clone <repo> uk-etdi && cd uk-etdi
cp .env.example .env                       # keys are optional — keyless sources work immediately
pip install -r backend/requirements.txt
python scripts/run_pipeline.py --no-notify # collect real events, score, generate opportunities
cd backend && uvicorn app.main:app --reload # dashboard: http://localhost:8000  ·  API docs: /api/docs
```

Or `docker compose up` (SQLite volume + built-in daily scheduler).

## What works out of the box (no API keys)
| Source | Type | Data |
|---|---|---|
| `football_fixtures` | official public JSON | Premier League, EFL Championship, Premiership Rugby full-season fixtures (~1,000 events) |
| `curated` | local JSON | Manually verified official events (graduations, freshers, etc.) |
| `ical_feeds` / `rss_feeds` / `venue_pages` | public feeds & schema.org pages | Add URLs in `config/sources.yaml` |

Add `TICKETMASTER_API_KEY` (free tier, 5k req/day) to unlock UK-wide concerts, theatre, comedy, family shows.
`eventbrite` and `jambase` connectors activate with their respective keys. Missing keys ⇒ source reports **DISABLED**, never FAILED.

## Phase 2 (coverage + quality + hardening)
* Key-less sources now live: fixture feeds (EPL, Championship, Scottish Prem, WSL, UCL-UK, Premiership Rugby), 13 Jockey Club racecourses, 6 arenas (JSON-LD), Experience Oxfordshire (JSON-LD, Crawl-delay honoured).
* Registries: `config/venues.yaml`, `config/institutions.yaml`, `config/councils.yaml`; SSRF allowlist `allowed_domains` in `config/sources.yaml`.
* Every event carries `source_confidence`, `event_quality_score`/`quality_level` (with reasons), `freshness_score`, `status_reason`; snapshots in `event_snapshots`.
* Marketing actions are gated (`config/scoring.yaml → action_gating`); opportunity v2 stores `score_components`.
* Dashboard: **Coverage**, **Data Quality** (click-through filters), source drilldown, event detail split into FACTS / MODELLED / RECOMMENDATION.
* CLI:
```bash
cd backend
python -m app.cli health
python -m app.cli coverage
python -m app.cli collect --source venue_pages --show 10   # or --city Oxford / --category sports
python -m app.cli pipeline --dry-run
python -m app.cli pipeline --no-notify
```
* Measured coverage and gaps: `docs/SOURCE_COVERAGE.md` (the Configured Coverage Index measures *our registry*, never "all UK events").

## Repository layout
```
backend/app/    collectors · processors · intelligence · orchestration · api · notifications · db
frontend/       zero-build dashboard (vanilla ES modules + Leaflet) served by FastAPI or any static host
config/         sources.yaml · categories.yaml · cities.yaml · venues.yaml · scoring.yaml
scripts/        run_pipeline.py · migrate.py · telegram_bot.py · send_digest.py · export_static.py
docs/           PRD · ARCHITECTURE · DATABASE · SOURCES · API · DEPLOYMENT · OPERATIONS
.github/        tests.yml · daily-pipeline.yml (UTC cron, DB persisted to a `data` branch)
```

## Principles
* **Only public data**, robots.txt respected, no CAPTCHA/login bypass, only factual metadata stored.
* **Explainable scoring** — weights in `config/scoring.yaml`, every score returns its reasons.
* **Modelled ≠ observed** — demand windows and attendance are labelled as modelled estimates everywhere.
* **Idempotent pipeline** — re-running never duplicates events (source id → fingerprint → fuzzy match).
* **Provider-agnostic** — SQLite→Postgres via `DATABASE_URL`; map tiles, notifications, and sheets are swappable.

## Tests
```bash
cd backend && python -m pytest -q      # 17 tests: normalisation, BST/GMT, classifier, dedupe, scoring, pipeline idempotency, API
```
See `docs/` for the full PRD, architecture, database schema, API reference, deployment and operations guides.
