"""End-to-end pipeline: config → sources → collect → validate → normalize → classify → geo → dedupe → persist →
changes → intelligence → opportunities → marketing → report → sync → notify → health. Idempotent by design."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from rapidfuzz import fuzz
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.base import CollectResult
from app.collectors.registry import build_collectors
from app.core.config import get_settings, reload_configs, scoring_config
from app.core.logging import get_logger
from app.db.models import (ErrorLog, Event, EventChange, EventSnapshot, EventSource, MarketingAction, Notification, Opportunity,
                           PipelineRun, RawEvent, Source, SourceRun, SystemHealth, utcnow)
from app.db.repositories.seed import seed_reference_data
from app.intelligence.demand_score import score_event
from app.intelligence.geography import GeographyEngine
from app.intelligence.marketing import generate_marketing_actions
from app.intelligence.quality import best_confidence, derive_status, freshness_score, is_source_silent, quality_for
from app.intelligence.taxi_opportunity import generate_opportunities
from app.notifications import sheets, telegram
from app.processors.change_detection import detect_changes
from app.processors.classify import classify
from app.processors.deduplicate import AUTO_MERGE_THRESHOLD, fingerprint, similarity
from app.processors.normalize import clean_title, normalize_title, normalize_url
from app.processors.validation import validate
from app.schemas.normalized import NormalizedEvent

log = get_logger("pipeline")


def _different_session(t_existing: str | None, t_incoming: str | None, min_gap_minutes: int = 120) -> bool:
    """True when both start times are known and differ by >= min_gap (e.g. 11:00 vs 14:00 matinee/evening)."""
    if not t_existing or not t_incoming or t_existing == t_incoming:
        return False
    try:
        h1, m1 = map(int, t_existing[:5].split(":")); h2, m2 = map(int, t_incoming[:5].split(":"))
    except ValueError:
        return False
    return abs((h1 * 60 + m1) - (h2 * 60 + m2)) >= min_gap_minutes

def _is_more_specific(new: str, old: str) -> bool:
    """A URL is 'more specific' when it has more path depth (event page beats listing page). Equal depth → keep old (stable)."""
    from urllib.parse import urlparse
    depth = lambda u: len([p for p in urlparse(u).path.split("/") if p])
    return depth(new) > depth(old)

class Pipeline:
    def __init__(self, db: Session, trigger: str = "manual", only_sources: list[str] | None = None, notify: bool = True):
        self.db = db
        self.trigger = trigger
        self.only_sources = only_sources
        self.notify = notify
        self.run = PipelineRun(trigger=trigger)
        self.stages: dict[str, Any] = {}
        self.errors = 0
        self.regressions: list[dict] = []

    # ------------------------------------------------------------------------------------------------------
    def _stage(self, name: str, fn, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            out = fn(*args, **kwargs)
            self.stages[name] = {"status": "ok", "ms": int((time.perf_counter() - t0) * 1000)}
            return out
        except Exception as exc:
            self.errors += 1
            self.stages[name] = {"status": "failed", "error": str(exc)[:300], "ms": int((time.perf_counter() - t0) * 1000)}
            self.db.add(ErrorLog(component=f"pipeline.{name}", message=str(exc)[:1000], pipeline_run_id=self.run.id))
            self.db.commit()
            log.exception("stage %s failed", name)
            return None

    def _recover_stale_runs(self) -> int:
        """Runs left RUNNING by a killed process (CI timeout, crash) are marked ABORTED so health/dashboards stay truthful."""
        cutoff = utcnow() - timedelta(hours=3)
        stale = self.db.scalars(select(PipelineRun).where(PipelineRun.status == "RUNNING", PipelineRun.started_at < cutoff)).all()
        for r in stale:
            r.status = "ABORTED"
            r.completed_at = utcnow()
            r.stages = {**(r.stages or {}), "recovery": "marked ABORTED by a later run (no completion recorded)"}
            for sr in self.db.scalars(select(SourceRun).where(SourceRun.pipeline_run_id == r.id, SourceRun.status == "RUNNING")).all():
                sr.status = "ABORTED"; sr.completed_at = utcnow()
        if stale:
            self.db.commit()
        return len(stale)

    def _retention(self) -> dict[str, int]:
        """Bounded growth (zero-cost SQLite in git): prune raw payloads, snapshots, health rows and old runs. Canonical events are NEVER deleted here."""
        r = get_settings()
        now = utcnow()
        out = {}
        out["raw_events"] = self.db.query(RawEvent).filter(RawEvent.fetched_at < now - timedelta(days=r.retention_raw_days)).delete(synchronize_session=False)
        out["event_snapshots"] = self.db.query(EventSnapshot).filter(EventSnapshot.taken_at < now - timedelta(days=r.retention_snapshot_days)).delete(synchronize_session=False)
        out["system_health"] = self.db.query(SystemHealth).filter(SystemHealth.recorded_at < now - timedelta(days=r.retention_health_days)).delete(synchronize_session=False)
        out["errors"] = self.db.query(ErrorLog).filter(ErrorLog.occurred_at < now - timedelta(days=r.retention_health_days)).delete(synchronize_session=False)
        old_runs = self.db.scalars(select(PipelineRun.id).where(PipelineRun.started_at < now - timedelta(days=r.retention_runs_days))).all()
        if old_runs:
            self.db.query(SourceRun).filter(SourceRun.pipeline_run_id.in_(old_runs)).delete(synchronize_session=False)
            self.db.query(RawEvent).filter(RawEvent.pipeline_run_id.in_(old_runs)).update({RawEvent.pipeline_run_id: None}, synchronize_session=False)
            self.db.query(EventChange).filter(EventChange.pipeline_run_id.in_(old_runs)).update({EventChange.pipeline_run_id: None}, synchronize_session=False)
            self.db.query(EventSnapshot).filter(EventSnapshot.pipeline_run_id.in_(old_runs)).update({EventSnapshot.pipeline_run_id: None}, synchronize_session=False)
            self.db.query(ErrorLog).filter(ErrorLog.pipeline_run_id.in_(old_runs)).delete(synchronize_session=False)
            self.db.query(Notification).filter(Notification.pipeline_run_id.in_(old_runs)).update({Notification.pipeline_run_id: None}, synchronize_session=False)
            out["pipeline_runs"] = self.db.query(PipelineRun).filter(PipelineRun.id.in_(old_runs)).delete(synchronize_session=False)
        # past events: keep, but mark COMPLETED so they drop out of active views (never delete canonical events)
        out["completed"] = self.db.query(Event).filter(Event.date_start < date.today() - timedelta(days=1), Event.status.in_(["SCHEDULED", "CONFIRMED", "SOLD_OUT", "RESCHEDULED"])) \
            .update({Event.status: "COMPLETED", Event.status_reason: "Event date has passed"}, synchronize_session=False)
        self.db.commit()
        return out

    def execute(self) -> PipelineRun:
        recovered = self._recover_stale_runs()
        self.db.add(self.run)
        self.db.commit()
        if recovered:
            self.stages["recovered_stale_runs"] = recovered
        log.info("pipeline run %s started (%s)", self.run.id, self.trigger)

        self._stage("load_configuration", self._load_configuration)
        results: list[CollectResult] = self._stage("collect", self._collect) or []
        raw_count = self._stage("validate_raw", self._store_raw, results) or 0
        valid: list[NormalizedEvent] = self._stage("normalize_validate", self._validate, results) or []
        persisted = self._stage("classify_geo_dedupe_persist", self._persist, valid) or {}
        self._stage("quality_freshness_status", self._quality)
        self._stage("intelligence", self._intelligence)
        self._stage("report_sync", self._sync_outputs)
        sent = self._stage("notify", self._notify) or 0
        self.stages["retention"] = self._stage("retention", self._retention) or {}
        self._stage("health", self._record_health)

        r = self.run
        r.events_raw = raw_count
        r.events_valid = len(valid)
        r.events_created = persisted.get("created", 0)
        r.events_updated = persisted.get("updated", 0)
        r.duplicates_removed = persisted.get("duplicates", 0)
        r.changes_detected = persisted.get("changes", 0)
        r.notifications_sent = sent
        r.errors = self.errors
        r.completed_at = utcnow()
        r.duration_seconds = round((r.completed_at - r.started_at).total_seconds(), 2)
        r.status = "SUCCESS" if self.errors == 0 else ("PARTIAL" if r.events_valid else "FAILED")
        r.stages = self.stages
        self.db.commit()
        log.info("pipeline run %s finished: %s in %ss", r.id, r.status, r.duration_seconds)
        return r

    # ---- stages --------------------------------------------------------------------------------------------
    def _load_configuration(self):
        from app.core.service_area import load_service_area
        reload_configs()
        seed_reference_data(self.db)
        sa = load_service_area(self.db)
        self.stages["service_area"] = {"cities": sa["cities"], "source": sa["source"]}

    def _collect(self) -> list[CollectResult]:
        collectors = build_collectors(self.only_sources)
        sources = {s.key: s for s in self.db.scalars(select(Source)).all()}
        results: list[CollectResult] = []
        for col in collectors:
            src = sources.get(col.name)
            if src is None or not src.enabled:
                continue
            self.run.sources_attempted += 1
            sr = SourceRun(source_id=src.id, pipeline_run_id=self.run.id)
            self.db.add(sr)
            res = col.run()
            results.append(res)
            sr.completed_at = utcnow()
            sr.status = res.status
            sr.events_collected = len(res.events)
            sr.response_ms = res.response_ms
            sr.error = res.error or ("; ".join(res.warnings)[:1000] or None)
            src.status = res.status
            src.last_response_ms = res.response_ms
            src.last_events_collected = len(res.events)
            src.last_error = sr.error
            if res.status in ("HEALTHY", "DEGRADED", "EMPTY"):
                src.last_success_at = utcnow()
                self.run.sources_successful += 1
            elif res.status in ("FAILED", "BLOCKED"):
                self.run.sources_failed += 1
                self.db.add(ErrorLog(component=f"collector.{col.name}", message=res.error or res.status.lower(), pipeline_run_id=self.run.id))
            # §64 per-source regression: zero (or a >50% drop) from a previously productive source is never "success"
            prev = self.db.scalar(select(SourceRun).where(SourceRun.source_id == src.id, SourceRun.id != sr.id, SourceRun.status.in_(("HEALTHY", "DEGRADED")))
                                  .order_by(SourceRun.id.desc()).limit(1))
            if prev and (prev.events_collected or 0) >= 10 and len(res.events) < 0.5 * prev.events_collected:
                msg = f"regression: {len(res.events)} events vs {prev.events_collected} in previous successful run"
                self.regressions.append({"source": src.key, "now": len(res.events), "previous": prev.events_collected})
                sr.error = (sr.error + "; " if sr.error else "") + msg
                self.db.add(ErrorLog(component=f"collector.{col.name}", message=msg, pipeline_run_id=self.run.id, details={"severity": "WARNING", "kind": "regression"}))
                log.warning("source %s %s", src.key, msg)
            self.db.commit()
        return results

    def _store_raw(self, results: list[CollectResult]) -> int:
        sources = {s.key: s.id for s in self.db.scalars(select(Source)).all()}
        count = 0
        for res in results:
            sid = sources.get(res.source_key)
            if sid is None:
                continue
            for ev in res.events:
                payload = json.loads(json.dumps(ev.raw, default=str))
                h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                exists = self.db.scalar(select(RawEvent.id).where(RawEvent.source_id == sid, RawEvent.source_external_id == ev.external_id, RawEvent.hash == h))
                if not exists:
                    self.db.add(RawEvent(source_id=sid, source_external_id=ev.external_id, payload=payload, source_url=ev.source_url, hash=h, pipeline_run_id=self.run.id))
                count += 1
        self.db.commit()
        return count

    def _validate(self, results: list[CollectResult]) -> list[NormalizedEvent]:
        valid: list[NormalizedEvent] = []
        rejected = Counter()
        for res in results:
            for ev in res.events:
                ok, problems = validate(ev)
                if ok:
                    valid.append(ev)
                else:
                    rejected.update(problems)
        self.stages["validation_rejections"] = dict(rejected)
        return valid

    def _persist(self, events: list[NormalizedEvent]) -> dict[str, int]:
        geo = GeographyEngine(self.db, use_postcode_api=False)
        sources = {s.key: s for s in self.db.scalars(select(Source)).all()}
        stats = Counter()
        seen_this_run: set[int] = set()
        for ev in events:
            src = sources[ev.source_key]
            title = clean_title(ev.title)
            g = geo.resolve(ev)
            venue = geo.get_or_create_venue(ev, g)
            city_name = g.city.name if g.city else ev.city_name
            fp = fingerprint(title, ev.date_start, venue.name if venue else ev.venue_name, city_name)
            cat, sub, _conf = classify(title, ev.category_hint, ev.description)

            # 1) same source + external id → update existing
            link = self.db.scalar(select(EventSource).where(EventSource.source_id == src.id, EventSource.external_id == ev.external_id))
            existing = link.event if link else None
            if existing is not None and _different_session(existing.time_start, ev.time_start, min_gap_minutes=1):
                # Linked event has a different known start time. If a sibling session for this exact time already exists
                # (title+time fingerprint), this id belongs to that session — re-point instead of flip-flopping TIME_CHANGED.
                sib = self.db.scalar(select(Event).where(Event.fingerprint == fingerprint(f"{title} {ev.time_start}", ev.date_start, venue.name if venue else ev.venue_name, city_name)))
                if sib is not None:
                    existing = sib
                elif _different_session(existing.time_start, ev.time_start):
                    existing = None  # same feed id reused for another session (e.g. 11:00 and 14:00 showings); smaller shifts = TIME_CHANGED
            # 2) exact fingerprint (same-day repeat sessions with a clearly different start time are separate events)
            if existing is None:
                existing = self.db.scalar(select(Event).where(Event.fingerprint == fp))
                # Same title/venue/day but a different *known* start time from the same source = a repeat session (matinee/
                # evening, hourly tours). Across sources a small gap is more likely a data discrepancy, so require ≥120 min.
                same_source = existing is not None and existing.primary_source == src.key
                if existing is not None and _different_session(existing.time_start, ev.time_start, min_gap_minutes=1 if same_source else 120):
                    fp = fingerprint(f"{title} {ev.time_start}", ev.date_start, venue.name if venue else ev.venue_name, city_name)
                    existing = self.db.scalar(select(Event).where(Event.fingerprint == fp))
                if existing:
                    stats["duplicates"] += 1
            # 3) fuzzy: same date, similar title/venue/city
            if existing is None:
                cands = self.db.scalars(select(Event).where(Event.date_start == ev.date_start)).all()
                best, best_conf = None, 0.0
                for c in cands:
                    # same rule as the fingerprint stage: any distinct start time from the same source is a separate session
                    if _different_session(c.time_start, ev.time_start, min_gap_minutes=1 if c.primary_source == src.key else 120):
                        continue
                    conf, _ = similarity(title, c.title, venue.name if venue else ev.venue_name, c.venue_name_raw, city_name, c.city_name_raw, True)
                    if conf > best_conf:
                        best, best_conf = c, conf
                if best and best_conf >= AUTO_MERGE_THRESHOLD:
                    existing = best
                    stats["duplicates"] += 1
                    log.debug("fuzzy merge %.2f: '%s' ~ '%s'", best_conf, title, best.title)

            now = utcnow()
            is_new = existing is None
            if is_new:
                existing = Event(canonical_event_id=uuid.uuid4().hex[:20], fingerprint=fp, title=title, normalized_title=normalize_title(title),
                                 date_start=ev.date_start, primary_source=src.key, first_seen_at=now, status=ev.status)
                self.db.add(existing)
                self.db.flush()
                self.db.add(EventChange(event_id=existing.id, pipeline_run_id=self.run.id, change_type="NEW", field=None, new_value=title))
                stats["created"] += 1
                stats["changes"] += 1
                changes: list[dict] = []
            else:
                changes = detect_changes(existing, ev, title=title, include_status=False)
                for ch in changes:
                    self.db.add(EventChange(event_id=existing.id, pipeline_run_id=self.run.id, **ch))
                stats["changes"] += len(changes)
                if changes:
                    stats["updated"] += 1
                    existing.last_updated_at = now
            seen_this_run.add(existing.id)
            # status engine (never downgrades on silence; absence from a source is not cancellation)
            date_changed = (not is_new) and any(c["field"] == "date_start" for c in changes)
            n_sources = 1 if is_new else len({l.source_id for l in existing.sources} | {src.id})  # distinct independent sources
            new_status, status_reason = derive_status(current_status=existing.status, incoming_status=ev.status, incoming_confidence=ev.source_confidence,
                                                      title=title, sold_out=ev.sold_out, source_count=n_sources, date_start=ev.date_start,
                                                      date_changed=date_changed)
            if not is_new and new_status != existing.status:
                self.db.add(EventChange(event_id=existing.id, pipeline_run_id=self.run.id, change_type="STATUS_CHANGED" if new_status not in ("CANCELLED", "POSTPONED") else new_status,
                                        field="status", old_value=existing.status, new_value=new_status))
                changes.append({"field": "status"})

            # apply fields (source priority: higher-priority source wins for conflicting fields)
            higher_priority = existing.primary_source is None or src.priority >= (sources.get(existing.primary_source).priority if sources.get(existing.primary_source) else 0)
            if higher_priority or existing.time_start is None:
                # keep the first-seen title when this is merely a fuzzy-equivalent listing from an equal-priority source
                # (prevents A/B title flip-flopping between two pages describing the same event)
                same_priority = existing.primary_source is not None and sources.get(existing.primary_source) is not None and src.priority == sources[existing.primary_source].priority
                if not (same_priority and existing.title != title and fuzz.token_set_ratio(normalize_title(existing.title), normalize_title(title)) >= 80):
                    existing.title = title
                    existing.normalized_title = normalize_title(title)
                existing.date_start = ev.date_start
                existing.date_end = ev.date_end or existing.date_end
                existing.time_start = ev.time_start or existing.time_start
                existing.time_end = ev.time_end or existing.time_end
                existing.primary_source = src.key if higher_priority else existing.primary_source
            existing.status = new_status
            existing.status_reason = status_reason
            existing.event_subtype = ev.event_subtype or existing.event_subtype
            existing.source_confidence = best_confidence([existing.source_confidence, ev.source_confidence])
            existing.source_count = n_sources
            existing.last_verified_at = now
            existing.description = existing.description or (ev.description[:300] if ev.description else None)
            existing.category, existing.subcategory = cat, sub
            existing.venue_id = venue.id if venue else existing.venue_id
            existing.venue_name_raw = ev.venue_name or existing.venue_name_raw
            existing.city_id = g.city.id if g.city else existing.city_id
            existing.city_name_raw = city_name or existing.city_name_raw
            existing.region_id = g.city.region_id if g.city else existing.region_id
            existing.postcode = g.postcode or existing.postcode
            existing.latitude = g.latitude if g.latitude is not None else existing.latitude
            existing.longitude = g.longitude if g.longitude is not None else existing.longitude
            existing.organizer = ev.organizer or existing.organizer
            new_official = normalize_url(ev.official_url)
            if new_official and (existing.official_url is None or _is_more_specific(new_official, existing.official_url)):
                existing.official_url = new_official  # never replace an event-specific URL with a generic listing page
            new_ticket = normalize_url(ev.ticket_url)
            if new_ticket and (existing.ticket_url is None or _is_more_specific(new_ticket, existing.ticket_url)):
                existing.ticket_url = new_ticket
            existing.venue_capacity = venue.capacity if venue and venue.capacity else ev.venue_capacity
            existing.recurrence = ev.recurrence or existing.recurrence
            existing.fingerprint = fp
            existing.last_seen_at = now

            if link is None:
                self.db.add(EventSource(event_id=existing.id, source_id=src.id, external_id=ev.external_id, source_url=ev.source_url))
            else:
                if link.event_id != existing.id:  # id was re-resolved to another session/event: re-point rather than leave a stale link
                    link.event_id = existing.id
                link.last_seen = now
                link.last_fetched = now
                link.source_url = ev.source_url or link.source_url
            if is_new or changes:
                snap = self._snapshot(existing)
                h = hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()
                last = self.db.scalar(select(EventSnapshot.snapshot_hash).where(EventSnapshot.event_id == existing.id).order_by(EventSnapshot.id.desc()).limit(1))
                if h != last:  # only store when the tracked facts actually differ from the last snapshot
                    self.db.add(EventSnapshot(event_id=existing.id, pipeline_run_id=self.run.id, reason="NEW" if is_new else "CHANGED", snapshot=snap, snapshot_hash=h))
                    stats["snapshots"] += 1
            self.db.flush()
        self.db.commit()
        return dict(stats)

    @staticmethod
    def _snapshot(e: Event) -> dict:
        return {"title": e.title, "date_start": e.date_start.isoformat() if e.date_start else None, "date_end": e.date_end.isoformat() if e.date_end else None,
                "time_start": e.time_start, "time_end": e.time_end, "venue_name_raw": e.venue_name_raw, "venue_id": e.venue_id, "city_id": e.city_id,
                "status": e.status, "status_reason": e.status_reason, "official_url": e.official_url, "ticket_url": e.ticket_url,
                "source_confidence": e.source_confidence, "source_count": e.source_count, "primary_source": e.primary_source}

    def _quality(self) -> dict:
        """Quality + freshness pass over every future event (also flags SOURCE SILENT; never deletes)."""
        from app.collectors.institutions import institutions_config
        school_conf = {i["name"].lower(): (i.get("school_event_confidence") or "LOW") for i in institutions_config() if i.get("type") in ("school", "college", "sixth_form")}
        today = date.today()
        now = utcnow()
        counts = Counter()
        for e in self.db.scalars(select(Event).where(Event.date_start >= today)).all():
            fresh = freshness_score(e.last_verified_at or e.last_seen_at, now)
            e.freshness_score = fresh
            if not e.source_confidence:  # rows persisted before Phase 2 or no longer returned by their source
                e.source_confidence = "UNVERIFIED"
            is_school = (e.category == "education" and (e.subcategory or "") in ("school", "college"))
            q = quality_for(source_confidence=e.source_confidence, time_start=e.time_start, venue_matched=e.venue_id is not None,
                            venue_named=bool(e.venue_name_raw), has_city=e.city_id is not None, official_url=e.official_url or e.ticket_url,
                            has_geo=bool(e.postcode or e.latitude is not None), category=e.category, source_count=e.source_count or 1,
                            freshness=fresh, is_school=is_school, school_confidence=school_conf.get((e.organizer or "").lower()))
            e.event_quality_score, e.quality_level, e.quality_reasons = q.score, q.level, q.reasons
            counts[q.level] += 1
            if is_source_silent(e.last_verified_at or e.last_seen_at, e.date_start, now):
                if not (e.status_reason or "").startswith("SOURCE SILENT"):
                    e.status_reason = f"SOURCE SILENT: not returned by any source since {(e.last_verified_at or e.last_seen_at).date().isoformat()}"
                counts["source_silent"] += 1
        self.db.commit()
        self.stages["quality_levels"] = dict(counts)
        return dict(counts)

    def _intelligence(self) -> None:
        today = date.today()
        events = self.db.scalars(select(Event).where(Event.date_start >= today)).all()
        opp_count = act_count = act_capped = dismissed = gated_events = 0
        max_actions = int((scoring_config().get("action_gating", {}) or {}).get("max_actions_per_run", 400))
        for e in events:
            res = score_event(category=e.category, date_start=e.date_start, date_end=e.date_end, time_start=e.time_start, time_end=e.time_end,
                              venue=e.venue, city=e.city, recurrence=e.recurrence, status=e.status)
            e.opportunity_score = res.score
            e.demand_level = res.demand_level
            e.marketing_priority = res.marketing_priority
            e.score_breakdown = res.as_dict()
            e.demand_windows = res.windows
            e.attendance_estimate = res.attendance_estimate
            e.attendance_confidence = res.attendance_confidence

            existing_opps = {o.opportunity_type: o for o in e.opportunities}
            new_opps = generate_opportunities(e)
            keep = set()
            for o in new_opps:
                keep.add(o["opportunity_type"])
                cur = existing_opps.get(o["opportunity_type"])
                if cur:
                    for k, v in o.items():
                        setattr(cur, k, v)
                else:
                    self.db.add(Opportunity(event_id=e.id, **o))
                    opp_count += 1
            for t, o in existing_opps.items():
                if t not in keep:
                    self.db.delete(o)

            existing_acts = {a.action_type: a for a in e.marketing_actions}
            proposed = generate_marketing_actions(e, today)
            if proposed:
                gated_events += 1
            for a in proposed:
                cur = existing_acts.get(a["action_type"])
                if cur:
                    if cur.status in ("NEW", "DISMISSED_AUTO"):  # don't overwrite user-managed actions
                        for k, v in a.items():
                            setattr(cur, k, v)
                        cur.status = "NEW"
                elif act_count < max_actions:
                    self.db.add(MarketingAction(event_id=e.id, **a))
                    act_count += 1
                else:
                    act_capped += 1
            if not proposed:  # gate closed (score/quality/status/service-area/horizon) → dismiss untouched NEW actions
                closed = "DISMISSED" if e.status in ("CANCELLED", "POSTPONED", "COMPLETED") else "DISMISSED_AUTO"
                for a in e.marketing_actions:
                    if a.status in ("NEW", "PLANNED") and closed == "DISMISSED" or a.status == "NEW":
                        a.status = closed
                        dismissed += 1
        self.run.opportunities_generated = opp_count
        self.run.actions_generated = act_count
        self.stages["marketing_gate"] = {"events_scored": len(events), "events_passing_gate": gated_events, "actions_created": act_count,
                                         "actions_capped": act_capped, "actions_auto_dismissed": dismissed, "max_actions_per_run": max_actions}
        self.db.commit()

    def _sync_outputs(self) -> None:
        from app.orchestration.reports import build_daily_report
        report = build_daily_report(self.db)
        self.stages["daily_report"] = {"events_today": report["summary"]["events_today"], "very_high": report["summary"]["very_high"]}
        if get_settings().google_sheets_webhook:
            ok, msg = sheets.push_report(report)
            self.stages["google_sheets"] = {"ok": ok, "message": msg}

    def _notify(self) -> int:
        """Send the daily digest through every configured NotificationProvider. Failures are recorded, never raised."""
        if not self.notify:
            return 0
        from app.orchestration.reports import build_daily_report, format_daily_digest
        from app.providers import get_notification_providers
        report = build_daily_report(self.db)
        text = format_daily_digest(report)
        sent = 0
        for provider in get_notification_providers():
            recipient = get_settings().telegram_chat_id if provider.key == "telegram" else None
            n = Notification(channel=provider.key, recipient=recipient or None, subject="daily_digest", body=text, pipeline_run_id=self.run.id)
            self.db.add(n)
            if not provider.is_configured():
                n.status, n.error = "SKIPPED", "not_configured"
                continue
            ok, msg = provider.send("daily_digest", text)
            n.status = "SENT" if ok else "FAILED"
            n.error = None if ok else msg
            n.sent_at = utcnow() if ok else None
            sent += 1 if ok else 0
        self.db.commit()
        return sent

    def _record_health(self) -> None:
        db_ok = True
        try:
            self.db.execute(select(func.count(Event.id)))
        except Exception:
            db_ok = False
        self.db.add(SystemHealth(component="database", status="HEALTHY" if db_ok else "FAILED"))
        self.db.add(SystemHealth(component="pipeline", status="HEALTHY" if self.errors == 0 else "DEGRADED", details={"run_id": self.run.id, "errors": self.errors}))
        for s in self.db.scalars(select(Source)).all():
            self.db.add(SystemHealth(component=f"source.{s.key}", status=s.status, details={"events": s.last_events_collected, "ms": s.last_response_ms}))
        self.db.commit()


def run_pipeline(db: Session, trigger: str = "manual", only_sources: list[str] | None = None, notify: bool = True) -> PipelineRun:
    return Pipeline(db, trigger=trigger, only_sources=only_sources, notify=notify).execute()
