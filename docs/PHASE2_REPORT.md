# Phase 2 — Final validation report (section 51)

Date: 18 Sep 2026 · sandbox · pipeline runs #6–#10 · tests: `34 passed, 1 skipped`.

## What was measured before vs after
| Metric | Before (run #5) | After (run #24) |
|---|---|---|
| Future canonical events | 902 | **1,667** |
| Sources with events | 2 (fixtures, curated) | 4 (fixtures, venue_pages, tourism, curated) |
| Cities with events | 38 / 56 | **60 / 75** |
| Categories | football, rugby | football, horse racing, rugby, concerts, comedy, theatre, community, arts, festival, family… |
| Horizons today/7d/30d/90d | 2 / 25 / 93 / 310 | **12 / 85 / 318 / 830** |
| Quality HIGH/MEDIUM/LOW | n/a | 388 / 1,271 / 3 |
| Marketing actions NEW | 6,003 (spam) | **745** (gated; 7,554 auto-dismissed, kept for audit) |
| Configured Coverage Index | n/a | 63 / 100 |
| Pipeline duration | 3.6 s | ~2.2 min (101 venue pages + 13 DMO pages, Crawl-delay honoured) |

## Delivered
Coverage: venue registry + collector (JSON→iCal→RSS→JSON-LD→detail pages, pagination), 13 racecourses, 6 arenas, Experience Oxfordshire,
3 new fixture feeds (UCL filtered to UK venues), institutions/councils/tourism registries, SSRF allowlist, robots + Crawl-delay.
Quality: source_confidence, event_quality_score/level with reasons, freshness_score/last_verified_at, status engine (CONFIRMED/POSTPONED/
CANCELLED/RESCHEDULED/SOLD_OUT/COMPLETED, never downgrades on silence), event_snapshots, SOURCE SILENT flagging, EMPTY vs FAILED.
Intelligence: opportunity v2 (additive score_components, confidence), action gating (score/quality/service-area/horizon/caps),
EMAIL + PARTNERSHIP actions with reason + recommended_date, service area from Settings (no hardcoded area).
Ops: CLI (health/sources/coverage/collect/pipeline --dry-run), retention, stale-run recovery, JSON logging, composite indexes,
page_size caps. Dashboard: Coverage, Data Quality, source drilldown, FACTS/MODELLED/RECOMMENDATION event detail, quality/confidence filters,
safe-URL rendering. Docs: SOURCE_COVERAGE.md, API/DATABASE/OPERATIONS/SOURCES/ARCHITECTURE updated.

## Known limits (honest)
* No key-less structured source found for Northern Ireland, universities, councils, most tourism boards, theatres, cricket — registered as
  EMPTY/BLOCKED/UNVERIFIED, not scraped. Ticketmaster/Eventbrite/JamBase stay DISABLED until keys are supplied.
* Multi-source corroboration is currently 0 % (each event comes from one source) so CONFIRMED is rare by design.
* `official_url` is absent for fixture-feed events (feeds don't publish one); venue capacity is null for 34 % of events (never invented).
* The Coverage Index measures our registry, not the UK.

## Final validation (runs 21–24, 18 Sep 2026)
* `pytest`: 44 passed, 1 skipped.
* `python -m app.cli health`: HEALTHY.
* Two consecutive full runs (#23, #24): **0 events created, 0 updated, 0 changes detected, 0 new snapshots** → pipeline is idempotent. 1,669 canonical events (1,667 future), 0 duplicate fingerprints; 13 sources attempted, 10 successful, 0 failed (3 DISABLED = missing optional keys).
* Fixes made during validation: `snapshot_hash` moved to its own migration (`0004`) so already-migrated databases get the column; same-day repeat sessions (≥2 h apart, e.g. 11:00 and 14:00 tours) are now separate events instead of flip-flopping one row; generic listing URLs never overwrite event-specific URLs; wording variants of the same title no longer count as changes; racecourse hint is now a *fallback* so "Wedding Show"/"Celebrate Christmas" at Cheltenham classify by title (horse_racing 159 → 119, community/business gained).
* Category mix (future): football 1,154 · community 146 · horse_racing 119 · concert 99 · rugby 92 · festival 21 · exhibition 14 · others ≤7.
