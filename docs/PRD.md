# Product Requirements — UK-ETDI

## Problem
A UK taxi operator needs a daily answer to: *what is happening, where, when, how big, and where should we focus drivers and marketing?*
Event information is scattered across ticketing APIs, fixture lists, venue sites, councils and universities, in inconsistent formats.

## Vision
Turn public event data into ranked, explained taxi demand intelligence and concrete marketing actions, every day, automatically, for free.

## Users
| Persona | Needs |
|---|---|
| Operations manager | Today/tomorrow event list, demand windows, hotspot venues, cancellations |
| Marketing lead | Which events deserve SEO/Ads/GBP/social attention, ready-made keywords and copy, action tracker |
| Owner | KPIs, trends, system health, zero running cost |

## Functional requirements (implemented)
| # | Module | Status |
|---|---|---|
| 1 | Source registry (`config/sources.yaml`, DB `sources`) | ✅ |
| 2 | Collectors: Ticketmaster, Eventbrite, JamBase, official fixtures, venue JSON-LD pages, iCal, RSS, university, council, curated | ✅ |
| 3 | Normaliser (UK dates, BST/GMT, TBC times, postcodes, statuses) | ✅ |
| 4 | Classifier (config keyword dictionaries, hint→title→description) | ✅ |
| 5 | Deduplicator (source id → exact fingerprint → fuzzy ≥0.88 auto-merge, 0.70–0.88 not merged) | ✅ |
| 6 | Change detector (NEW, UPDATED, DATE/TIME/VENUE_CHANGED, CANCELLED, POSTPONED, STATUS_CHANGED) | ✅ |
| 7 | Geography engine (venue/city registry + aliases + fuzzy, nearest-city, optional postcodes.io) | ✅ |
| 8 | Venue intelligence (sourced capacity, transport distances, importance) | ✅ |
| 9 | Demand scoring 0–100, 8 weighted components, reasons list | ✅ |
| 10 | Taxi opportunity engine (10 journey types, modelled windows) | ✅ |
| 11 | Marketing engine (SEO, Google Ads, Meta Ads, GBP, social, landing page, WhatsApp) | ✅ |
| 12 | Database (18 tables, SQLite, SQLAlchemy → Postgres-ready) | ✅ |
| 13 | REST API (standard envelope, pagination, errors) | ✅ |
| 14 | Dashboard (home KPIs, map, feed, detail, opportunities, actions, calendar, analytics, changes, sources, system, settings) | ✅ |
| 15 | Notifications (Telegram digest + bot commands, email stub, Sheets optional) | ✅ |
| 16 | Orchestrator (17-stage pipeline, run model, manual/API/cron/in-process scheduler) | ✅ |
| 17 | System health + source health | ✅ |
| 18 | Configuration manager (env + YAML + DB settings, secrets never exposed) | ✅ |
| 19 | Audit: raw payloads, source runs, event changes, errors, notifications | ✅ |
| 20 | Tests (pytest, CI) | ✅ |

## Non-functional
* £0 infra: GitHub Actions cron + SQLite committed to a data branch + static/any free host for the dashboard.
* Pipeline < 60 s for ~1,000 events on a 2-vCPU runner (measured ≈ 4–6 s).
* Every collector fails independently; pipeline status PARTIAL rather than FAILED when some sources fail.
* Legal/ethical: public data only, robots.txt, no copyrighted descriptions stored.

## Out of scope (v1)
Historical taxi trip ingestion (would convert modelled windows into calibrated forecasts), authentication/multi-tenant, paid map providers, LLM-based classification.

## Success metrics
Daily digest delivered by 07:00 local; ≥90 % events geo-resolved to a city; 0 duplicate canonical events per fixture; marketing actions actioned/dismissed within 48 h.

## Phase 2 status (18 Sep 2026)
Delivered: coverage expansion via key-less official sources (1,662 future events, 60/75 cities), venue/institution/council registries,
trust hierarchy + quality/freshness/status engines, snapshots, source health incl. SOURCE SILENT, Configured Coverage Index, dashboard
Coverage/Data Quality/drilldown/FACTS-MODELLED-RECOMMENDATION, structured service area, opportunity v2, action gating, digest v2, CLI,
retention, recovery, SSRF + frontend URL hardening, 44 tests. Open gaps: NI, universities/councils (no public structured feeds found), theatre, cricket; API sources need keys.
