# Sources

| Key | Type | Key required | Coverage | Notes |
|---|---|---|---|---|
| ticketmaster | API (Discovery v2) | `TICKETMASTER_API_KEY` (free, 5k/day) | UK concerts, sport, theatre, comedy, family | Paged to TM's 1,000-item cap per query; add city/segment splits in config for deeper coverage |
| eventbrite | API v3 | `EVENTBRITE_API_KEY` | Own-organisation events or explicit public event IDs | Public search was removed by Eventbrite in 2020 — not a discovery source any more |
| jambase | API | `JAMBASE_API_KEY` (free dev tier) | Live music GB | |
| football_fixtures | Official public JSON (fixturedownload.com) | none | PL, Championship, Premiership Rugby full season | Kick-off UTC → London; `00:00` = time TBC; scores present ⇒ status COMPLETED |
| venue_pages | Public HTML with schema.org `Event` JSON-LD | none | Any venue that publishes structured data | robots.txt checked before each fetch; add `{url, venue, city}` entries |
| ical_feeds / university | iCal | none | Councils, universities, venues | add `{name, url, city, category_hint}` |
| rss_feeds / council | RSS (+ev: namespace) | none | Councils "what's on" | date parsed from `ev:startdate` or text |
| curated | Local JSON | none | Verified official one-offs (graduations, freshers) | `data/curated_events.json` |

## Contract
```python
class Collector:
    name: str
    def health_check(self) -> HealthResult      # HEALTHY / DEGRADED / FAILED / DISABLED
    def collect(self, config) -> CollectResult  # runs fetch → parse → normalize
    def parse(self, payload) -> Iterable[dict]
    def normalize(self, item) -> NormalizedEvent | None
```
`Collector.run()` wraps collect with timing, exception isolation and status classification. `fetch()` provides timeout, 3 retries with exponential backoff, 429/5xx handling and optional robots.txt enforcement.

## Adding a source
1. Implement a `Collector` subclass in `backend/app/collectors/`.
2. Register it in `collectors/registry.py`.
3. Add config under `sources:` in `config/sources.yaml` (enabled, type, priority, requires_key, feed list).
4. Run `python scripts/run_pipeline.py --sources <key> --no-notify` and check `/api/sources`.

## Compliance checklist
Official API or feed preferred → robots.txt honoured → rate limits (sequential, ≤5 pages) → no auth/paywall/CAPTCHA bypass → metadata only stored → source URL retained for attribution.

## Phase 2 registries
* `config/venues.yaml` — `official_website`, `official_events_url`, `events_json_url`, `ical_url`, `rss_url`, `detail_pattern`,
  `max_detail_pages`, `page_pattern` + `max_listing_pages`, `category_hint`, `source_priority`, `verification_status`, `last_probed`, `enabled`.
  Fallback chain per venue: JSON → iCal → RSS → JSON-LD listing (paginated) → detail pages.
* `config/institutions.yaml` — universities/colleges/schools; registry-only, public calendars only, `school_event_confidence`.
* `config/councils.yaml` — councils + tourism boards (`kind: tourism`).
* `allowed_domains` in `sources.yaml` is an SSRF allowlist enforced on every outbound request (plus private-range and scheme checks,
  redirect hops re-validated, 10 MB body cap, robots.txt + `Crawl-delay` honoured).

## Trust hierarchy → `source_confidence`
OFFICIAL (venue/organiser/governing body) > CURATED ≈ TRUSTED (republished official schedules, licensed APIs) > SECONDARY (aggregators) > UNVERIFIED.
Set per collector class; feeds into `event_quality_score` (weights in `scoring.yaml → source_confidence_points`).

See `docs/SOURCE_COVERAGE.md` for the measured table and gap analysis.
