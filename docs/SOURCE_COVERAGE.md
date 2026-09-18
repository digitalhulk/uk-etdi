# Source Coverage — measured, not claimed (Phase 3 update at top; Phase 2 baseline kept below)

Measured on **18 Sep 2026** from the sandbox (pipeline run #9, `python -m app.cli coverage`). Every number below comes from the
database or a live probe; nothing is estimated. **This is Configured/Observed coverage of the registry we operate — it is not,
and never will be, "all UK events".**

Status vocabulary: `ACTIVE` (returned ≥1 future event), `EMPTY` (reachable, 0 structured events), `DEGRADED` (some endpoints
failed), `BLOCKED` (401/403/406/robots — never retried automatically), `DISABLED` (needs a key or switched off in config),
`UNVERIFIED` (registered, no structured endpoint found yet), `SOURCE SILENT` (previously active, no success for >3 days).

## Phase 3 headline (measured 18 Sep 2026, pipeline run #40)

| Metric | Phase 2 | Phase 3 |
|---|---|---|
| Configured Coverage Index | 63 / 100 | **72 / 100** |
| Future canonical events | 1,667 | **2,920** |
| Horizons today / 7d / 30d / 90d | 12 / 85 / 320 / 835 | **15 / 125 / 494 / 1,338** |
| Cities / venues with ≥1 future event | 60 / 123 | **62 / 163** |
| Quality HIGH / MEDIUM / LOW | 391 / 1,273 / 3 | **1,582 / 1,336 / 2** |
| Confidence OFFICIAL / TRUSTED / UNVERIFIED | 246 / 1,419 / 4 | **1,386 / 1,532 / 2** |
| Northern Ireland future events | 0 | **3** (NI home internationals, Windsor Park, Belfast — UEFA Nations League feed) |
| Three consecutive runs 0/0/0/0 | yes | yes (runs 38–40) |

New in Phase 3 (all key-less, robots-checked, structured data only):

| Source | Type | Future events | Notes |
|---|---|---|---|
| football_fixtures + UEFA Nations League / Europa / Conference / Scottish Premiership (UK venues only) | JSON | 1,277 total | adds Scotland, Wales, NI internationals |
| venue_pages — Nimax Theatres ×5 producing (Apollo 132, Lyric 374, Vaudeville 515, Garrick 37, Duchess 7) | WP REST → per-performance JSON-LD | 1,065 | West End; every performance is its own session (matinee/evening) |
| venue_pages — Spektrix RSS (Royal Lyceum, Dundee Rep, B:Music, Oxford Playhouse) | RSS with dated titles | 40 | Eden Court removed (news-only feed) |
| tourism — Visit Leicester | WP REST + detail JSON-LD | 60 | East Midlands community/arts |
| universities — Aberdeen (RSS, pubDate = event date), Cambridge talks (ICS) | RSS / ICS | 41 | first working institution feeds; registry-only, no crawling |

**Evaluated and NOT adopted in Phase 3** (do not retry): northwales.com, edinburgh.org, essexcricket, wccc (WP REST but no detail JSON-LD → would need HTML date parsing); all NI venues (JS-only or connection refused: SSE Arena, Waterfront, Ulster Hall, MAC, Lyric Belfast, GOH, Millennium Forum, Island Arts Centre); all county cricket grounds; fixturedownload has no UK domestic cricket / Super League feeds; Eventbrite/Ticketmaster/JamBase stay DISABLED until a key is set (dashboard shows the reason).

Cities still at 0 future events: Barnsley, Blackpool, Huddersfield, Livingston, Luton, Newcastle-under-Lyme, Plymouth, Reading, Rotherham, Swindon, Wigan, Worcester, York — none has a discoverable key-less structured feed in our registry; they are reported as gaps, not filled with guesses.

## Phase 2 headline (all future events)

| Metric | Value |
|---|---|
| Configured Coverage Index | **63 / 100** (weighted share of key-less configured targets that are ACTIVE) |
| Future canonical events | 1,667 (was 902 before Phase 2) |
| Horizons today / 7d / 30d / 90d | 12 / 85 / 318 / 830 |
| Cities with ≥1 future event | 60 / 75 configured (was 38 / 56) |
| Venues with events | 123 / 158 registered |
| Quality HIGH / MEDIUM / LOW | 388 / 1,271 / 3 |
| Source confidence OFFICIAL / TRUSTED / CURATED | 245 / 1,413 / 1 |
| Regions with 0 events | Northern Ireland (no key-less structured source found) |

## Source table

| Source | Type | Coverage | Status | Auth | Future events | Last success | Failure rate (last 20 runs) | Rate-limit / politeness | Legal / robots | Priority |
|---|---|---|---|---|---|---|---|---|---|---|
| football_fixtures (fixturedownload.com) | JSON feed | EPL, Championship, Premiership Rugby, Scottish Premiership, WSL, UCL (UK venues only) | ACTIVE | none | 1,245 | 2026-09-18 | 0.0 | 6 requests/run | public JSON, no robots restriction | 85 |
| venue_pages — Jockey Club ×13 | JSON-LD (HTML) | Cheltenham, Aintree, Epsom, Newmarket, Sandown, Kempton, Haydock, Exeter, Wincanton, Warwick, Huntingdon, Nottingham, Carlisle | ACTIVE | none | 159 | 2026-09-18 | 0.0 | 1 page/course, 0.6 s/host | robots allows `/events-tickets/` (disallows `/*?` — never queried with params) | 85 |
| venue_pages — ASM/AXS arenas ×5 | JSON-LD listing + ≤20 detail pages | The O2, OVO Arena Wembley, AO Arena, Utilita Arena Birmingham, first direct (bank) arena, Utilita Arena Sheffield | ACTIVE | none | 86 | 2026-09-18 | 0.0 | ≤21 pages/venue, 0.6 s/host | robots allow; JSON-LD is intended for machine reading | 80 |
| venue_pages — Utilita Arena Newcastle | JSON-LD | — | DISABLED (UNVERIFIED) | none | 0 | never | — | — | TLS handshake fails for automated clients; 0 events when reachable | 80 |
| tourism — Experience Oxfordshire | JSON-LD on paginated listing | Oxfordshire (Oxford + towns) | ACTIVE | none | 171 | 2026-09-18 | 0.0 | ≤12 pages, **Crawl-delay 3 s honoured** | robots disallows `/*?` ⇒ tribe REST API and `?ical=1` deliberately NOT used | 62 |
| tourism — NewcastleGateshead | JSON-LD | Tyneside | UNVERIFIED | none | 0 | — | — | 1 page | robots allow; listing exposed 1 event on probe | 62 |
| tourism — Visit Leeds / London / Wales / Liverpool / Nottinghamshire | HTML | — | EMPTY / BLOCKED / BLOCKED / UNVERIFIED / UNVERIFIED | none | 0 | — | — | — | 403 or JS-only; not scraped | 62 |
| councils ×8 (Manchester, Glasgow, Edinburgh, Birmingham, Cardiff, Leeds, Bristol, Belfast) | HTML | — | BLOCKED ×5 / UNVERIFIED ×3 | none | 0 | — | — | — | gov.uk sites 403 automated clients or have no feed; registered for gap reporting only | 60 |
| universities ×15 | HTML | — | EMPTY ×11 / BLOCKED ×4 | none | 0 | — | — | — | ~50 conventional ICS/RSS/tribe paths probed: none exist; ox/leeds/cardiff/durham/qmul/city/ntu/dundee/ulster 403 | 65 |
| colleges / schools | registry | — | EMPTY (no targets) | none | 0 | — | — | — | registry-only by design; add `ical_url` per institution | 55 / 45 |
| ical_feeds / rss_feeds | feeds | user-supplied | EMPTY (no feeds configured) | none | 0 | — | — | — | — | 60 / 50 |
| curated (data/curated_events.json) | file | manual | ACTIVE | none | 1 | 2026-09-18 | 0.0 | — | — | 40 |
| ticketmaster | API | UK-wide | DISABLED | `TICKETMASTER_API_KEY` | 0 | — | — | 5 req/s free tier | ToS: metadata only | 100 |
| eventbrite | API | org events | DISABLED | `EVENTBRITE_API_KEY` | 0 | — | — | — | — | 90 |
| jambase | API | music | DISABLED | `JAMBASE_API_KEY` | 0 | — | — | — | — | 70 |

## Probed and rejected (do not retry)

* **JS-rendered, no JSON-LD/feeds**: OVO Hydro, Utilita Arena Sheffield/Nottingham (Motorpoint), Barbican, Roundhouse, Eventim Apollo, O2 Academies, ExCeL, all football/cricket stadium sites, Silverstone, Wimbledon, ECB, National Theatre, RSC, LW Theatres, ATG, Doncaster racecourse, The Hundred, Visit Leeds (Simpleview).
* **403/406/blocked**: Co-op Live, Royal Albert Hall, Southbank Centre, Ascot, Goodwood, AXS, Gigantic, See Tickets, Bandsintown, Skiddle, visitlondon, visitwales, visitharrogate, visitcornwall, bp pulse LIVE, several ac.uk and gov.uk sites.
* **404/connection errors**: 3Olympia, York/Chester/Newbury racecourses, Arena Racing Company, M&S Bank Arena, Principality Stadium, Lord's, P&J Live, Odyssey Belfast, NEC, ACC Liverpool.
* fixturedownload feeds that do not exist: FA Cup, EFL Cup, League One/Two, Super League, cricket, Six Nations.

## Gap analysis

| Dimension | Covered | Gaps |
|---|---|---|
| Category | football, rugby, horse racing, arena concerts/comedy, Oxfordshire community | cricket, theatre (West End), festivals (national), nightlife, conferences, education (no institution feeds) |
| Region | South East 308, Greater London 295, North West 251, West Midlands 177, Scotland 162, South West 109, East Midlands 83, East of England 82, Yorkshire 65, North East 62, Wales 60 | **Northern Ireland 0** |
| Cities (0 events) | — | Barnsley, Belfast, Blackpool, Cambridge, Huddersfield, Livingston, Luton, Newcastle-under-Lyme, Plymouth, Reading, Rotherham, Swindon, Wigan, Worcester, York |
| Venue type | stadiums (fixtures), arenas (6), racecourses (13) | theatres, concert halls, exhibition centres, festival sites |
| Source type | official feeds, official venue JSON-LD, one DMO | ticketing APIs (keys optional), councils, universities |
| Horizon | 90-day window well populated by fixtures; arenas publish ~3–6 months ahead | beyond 90 days depends on fixture releases |
| Data completeness | time 99.9 %, city 99.5 %, coords 99.5 % | official_url missing for 74.9 % (fixture feeds publish no per-match URL — by design), venue_capacity null 33.7 % (never invented) |

## How to extend (zero cost, legal)

1. Add the domain to `allowed_domains` in `config/sources.yaml` (SSRF allowlist).
2. Add a venue with `official_events_url` (+ `detail_pattern`/`max_detail_pages` if the listing truncates), or an institution/council
   with `ical_url` / `rss_url` / `events_url`. Set `verification_status: UNVERIFIED` until a run proves it.
3. `python -m app.cli collect --source venue_pages --show 10` → check status; the Coverage page will show it as ACTIVE/EMPTY.
4. Optional keys (`TICKETMASTER_API_KEY` …) flip API sources from DISABLED to ACTIVE with no code change.
