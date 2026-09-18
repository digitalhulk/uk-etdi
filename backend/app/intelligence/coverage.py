"""Coverage & source-health reporting (Phase 2).

Never claims national coverage. Two measured notions:
  * Observed Sources   — what the registries (sources.yaml, venues.yaml, institutions.yaml, councils.yaml) configure and what
                         each target actually returned in the last runs.
  * Configured Coverage Index (0..100) — share of *configured* targets that are ACTIVE and returned ≥1 future event,
                         weighted by target type. It is an index of how much of our own registry is working, NOT of the UK.
Everything is computed from DB rows + config; no invented numbers.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import cities_config, load_config, sources_config, venues_config
from app.db.models import City, Event, EventSource, PipelineRun, Source, SourceRun, Venue

HORIZONS = {"today": 0, "7d": 7, "30d": 30, "90d": 90}
TARGET_WEIGHTS = {"source": 3.0, "venue": 1.0, "council": 1.0, "tourism": 1.0, "university": 0.5, "college": 0.25, "school": 0.25}


def _future(stmt, today: date):
    return stmt.where(Event.date_start >= today)


def horizon_counts(db: Session, today: date | None = None, **where) -> dict[str, int]:
    today = today or date.today()
    out = {}
    for label, days in HORIZONS.items():
        stmt = select(func.count(Event.id)).where(Event.date_start >= today, Event.date_start <= today + timedelta(days=days))
        for col, val in where.items():
            stmt = stmt.where(getattr(Event, col) == val)
        out[label] = int(db.scalar(stmt) or 0)
    return out


def configured_targets() -> list[dict[str, Any]]:
    """Flat list of every configured collection target with its declared verification status."""
    targets: list[dict[str, Any]] = []
    for key, cfg in sources_config().items():
        targets.append({"kind": "source", "key": key, "name": key, "enabled": bool(cfg.get("enabled", True)), "requires_key": cfg.get("requires_key"),
                        "declared_status": None, "city": None, "type": cfg.get("type")})
    for v in venues_config():
        if v.get("official_events_url") or v.get("events_json_url") or v.get("ical_url") or v.get("rss_url"):
            targets.append({"kind": "venue", "key": v["name"], "name": v["name"], "enabled": bool(v.get("enabled", True)), "city": v.get("city"),
                            "declared_status": v.get("verification_status"), "source_key": "venue_pages", "type": v.get("venue_type")})
    for c in load_config("councils.yaml").get("councils", []):
        targets.append({"kind": c.get("kind", "council"), "key": c["council"], "name": c["council"], "enabled": bool(c.get("enabled", True)), "city": c.get("city"),
                        "declared_status": c.get("verification_status"), "source_key": "tourism" if c.get("kind") == "tourism" else "councils", "type": c.get("kind")})
    for i in load_config("institutions.yaml").get("institutions", []):
        kind = {"university": "university", "college": "college", "sixth_form": "college", "school": "school"}.get(i.get("type"), "school")
        targets.append({"kind": kind, "key": i["name"], "name": i["name"], "enabled": bool(i.get("enabled", True)), "city": i.get("city"),
                        "declared_status": i.get("verification_status"), "source_key": {"university": "universities", "college": "colleges", "school": "schools"}[kind],
                        "type": i.get("type")})
    return targets


def source_health(db: Session, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    out = []
    now = datetime.utcnow()
    for s in db.scalars(select(Source).order_by(Source.priority.desc())).all():
        runs = db.scalars(select(SourceRun).where(SourceRun.source_id == s.id).order_by(SourceRun.id.desc()).limit(20)).all()
        n = len(runs)
        failed = sum(1 for r in runs if r.status == "FAILED")
        week = [r for r in runs if r.started_at >= now - timedelta(days=7)]
        avg7 = round(sum(r.events_collected for r in week) / len(week), 1) if week else None
        last_fail = next((r for r in runs if r.status == "FAILED"), None)
        # SOURCE SILENT (§20): previously productive source now returning zero for ≥3 consecutive runs
        recent0 = [r.events_collected for r in runs[:3]]
        ever = any(r.events_collected > 0 for r in runs[3:]) or (s.last_events_collected or 0) > 0
        silent_zero = len(recent0) == 3 and all(x == 0 for x in recent0) and any(r.events_collected > 0 for r in runs[3:])
        fut = int(db.scalar(select(func.count(func.distinct(EventSource.event_id))).join(Event, Event.id == EventSource.event_id)
                            .where(EventSource.source_id == s.id, Event.date_start >= today)) or 0)
        last_ok = s.last_success_at
        silent = bool(s.enabled and s.status not in ("DISABLED",) and ((last_ok and (now - last_ok) > timedelta(days=3)) or silent_zero))
        status = s.status
        if not s.enabled:
            status = "DISABLED"
        elif s.status in ("HEALTHY", "DEGRADED") and (s.last_events_collected or 0) == 0:
            status = "EMPTY"
        if silent:
            status = "SOURCE SILENT"
        cfg = sources_config().get(s.key, {})
        out.append({"id": s.id, "key": s.key, "type": s.type, "priority": s.priority, "enabled": s.enabled, "status": status, "raw_status": s.status,
                    "requires_key": cfg.get("requires_key"), "auth": "key" if cfg.get("requires_key") else "none",
                    "last_success_at": last_ok.isoformat() if last_ok else None, "last_failure_at": last_fail.started_at.isoformat() if last_fail else None,
                    "last_events_collected": s.last_events_collected, "events_7_day_average": avg7, "failure_count": failed,
                    "future_events": fut, "runs_sampled": n, "failure_rate": round(failed / n, 2) if n else None,
                    "avg_response_ms": int(sum((r.response_ms or 0) for r in runs) / n) if n else None, "last_error": (s.last_error or "")[:300] or None})
    return out


def coverage_report(db: Session, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    targets = configured_targets()
    # events per configured venue target
    venue_future = dict(db.execute(select(Venue.name, func.count(Event.id)).join(Event, Event.venue_id == Venue.id).where(Event.date_start >= today).group_by(Venue.name)).all())
    org_future = dict(db.execute(select(Event.organizer, func.count(Event.id)).where(Event.date_start >= today, Event.organizer.is_not(None)).group_by(Event.organizer)).all())
    src_rows = {r["key"]: r for r in source_health(db, today)}

    idx_num = idx_den = 0.0
    by_status = Counter()
    for t in targets:
        w = TARGET_WEIGHTS.get(t["kind"], 1.0)
        if t["kind"] == "source":
            sh = src_rows.get(t["key"])
            got = sh["future_events"] if sh else 0
            status = (sh or {}).get("status") or ("DISABLED" if not t["enabled"] else "UNVERIFIED")
            if status in ("HEALTHY", "DEGRADED") and got == 0:
                status = "EMPTY"
            if status == "HEALTHY":
                status = "ACTIVE"
        else:
            got = venue_future.get(t["key"], 0) if t["kind"] == "venue" else org_future.get(t["key"], 0)
            status = "DISABLED" if not t["enabled"] else ("ACTIVE" if got > 0 else (t.get("declared_status") or "EMPTY"))
        t["future_events"] = int(got)
        t["status"] = status
        by_status[status] += 1
        if t["enabled"] and t.get("requires_key") is None:
            idx_den += w
            if status == "ACTIVE":
                idx_num += w
    index = int(round(100 * idx_num / idx_den)) if idx_den else 0

    # gap analysis
    cats = db.execute(select(Event.category, Event.subcategory, func.count(Event.id)).where(Event.date_start >= today).group_by(Event.category, Event.subcategory)).all()
    cities_cfg = cities_config()
    city_rows = db.execute(select(City.name, City.region_id, func.count(Event.id)).outerjoin(Event, (Event.city_id == City.id) & (Event.date_start >= today)).group_by(City.id)).all()
    city_counts = {n: c for n, _r, c in city_rows}
    city_gaps = sorted([c["name"] for c in cities_cfg if city_counts.get(c["name"], 0) == 0], key=str)
    region_counts = Counter()
    for c in cities_cfg:
        region_counts[c.get("region") or "Unknown"] += city_counts.get(c["name"], 0)
    src_counts = dict(db.execute(select(Event.primary_source, func.count(Event.id)).where(Event.date_start >= today).group_by(Event.primary_source)).all())
    conf_counts = dict(db.execute(select(Event.source_confidence, func.count(Event.id)).where(Event.date_start >= today).group_by(Event.source_confidence)).all())
    quality_counts = dict(db.execute(select(Event.quality_level, func.count(Event.id)).where(Event.date_start >= today).group_by(Event.quality_level)).all())
    status_counts = dict(db.execute(select(Event.status, func.count(Event.id)).group_by(Event.status)).all())
    venues_total = int(db.scalar(select(func.count(Venue.id))) or 0)
    venues_with = int(db.scalar(select(func.count(func.distinct(Event.venue_id))).where(Event.date_start >= today, Event.venue_id.is_not(None))) or 0)
    silent = int(db.scalar(select(func.count(Event.id)).where(Event.date_start >= today, Event.status_reason.like("SOURCE SILENT%"))) or 0)
    last_run = db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)).first()

    return {
        "as_of": today.isoformat(),
        "disclaimer": "Configured Coverage Index measures how much of OUR configured registry is returning events. It is not a measure of all UK events.",
        "configured_coverage_index": index,
        "index_basis": {"weighted_active": round(idx_num, 2), "weighted_configured_keyless": round(idx_den, 2), "weights": TARGET_WEIGHTS},
        "targets_by_status": dict(by_status),
        "targets_by_kind": dict(Counter(t["kind"] for t in targets)),
        "targets": targets,
        "events": {"future_total": int(sum(src_counts.values())), "horizons": horizon_counts(db, today), "by_source": src_counts,
                   "by_category": [{"category": c, "subcategory": s, "count": n} for c, s, n in sorted(cats, key=lambda r: -r[2])],
                   "by_source_confidence": conf_counts, "by_quality": quality_counts, "by_status": status_counts, "source_silent": silent},
        "geography": {"cities_configured": len(cities_cfg), "cities_with_events": sum(1 for v in city_counts.values() if v > 0),
                      "cities_without_events": city_gaps, "by_region": dict(region_counts.most_common()),
                      "top_cities": sorted(({"city": k, "count": v} for k, v in city_counts.items() if v), key=lambda r: -r["count"])[:25],
                      "venues_registered": venues_total, "venues_with_events": venues_with},
        "sources": list(src_rows.values()),
        "last_pipeline_run": None if not last_run else {"id": last_run.id, "status": last_run.status, "started_at": last_run.started_at.isoformat(),
                                                        "duration_seconds": last_run.duration_seconds, "stages": last_run.stages},
    }


def data_quality_report(db: Session, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    base = select(func.count(Event.id)).where(Event.date_start >= today)
    total = int(db.scalar(base) or 0)

    def pct(n: int) -> float:
        return round(100 * n / total, 1) if total else 0.0

    missing = {
        "time_start": int(db.scalar(base.where(Event.time_start.is_(None))) or 0),
        "venue_id": int(db.scalar(base.where(Event.venue_id.is_(None))) or 0),
        "city_id": int(db.scalar(base.where(Event.city_id.is_(None))) or 0),
        "official_url": int(db.scalar(base.where(Event.official_url.is_(None), Event.ticket_url.is_(None))) or 0),
        "coordinates": int(db.scalar(base.where(Event.latitude.is_(None))) or 0),
        "venue_capacity": int(db.scalar(base.where(Event.venue_capacity.is_(None))) or 0),
        "category_other": int(db.scalar(base.where(Event.category == "other")) or 0),
    }
    quality = dict(db.execute(select(Event.quality_level, func.count(Event.id)).where(Event.date_start >= today).group_by(Event.quality_level)).all())
    conf = dict(db.execute(select(Event.source_confidence, func.count(Event.id)).where(Event.date_start >= today).group_by(Event.source_confidence)).all())
    fresh = db.execute(select(func.avg(Event.freshness_score), func.min(Event.freshness_score)).where(Event.date_start >= today)).one()
    multi = int(db.scalar(base.where(Event.source_count >= 2)) or 0)
    avg_q = db.scalar(select(func.avg(Event.event_quality_score)).where(Event.date_start >= today))
    dup_titles = db.execute(select(Event.normalized_title, Event.date_start, func.count(Event.id)).where(Event.date_start >= today)
                            .group_by(Event.normalized_title, Event.date_start).having(func.count(Event.id) > 1)).all()
    return {
        "as_of": today.isoformat(), "future_events": total,
        "quality_levels": quality, "avg_quality_score": round(float(avg_q), 1) if avg_q is not None else None,
        "source_confidence": conf, "multi_source_events": multi, "multi_source_pct": pct(multi),
        "freshness": {"avg": round(float(fresh[0]), 1) if fresh[0] is not None else None, "min": fresh[1]},
        "missing": {k: {"count": v, "pct": pct(v)} for k, v in missing.items()},
        "possible_duplicates": [{"title": t, "date": d.isoformat(), "count": n} for t, d, n in dup_titles[:50]],
        "possible_duplicates_total": len(dup_titles),
        "source_silent": int(db.scalar(base.where(Event.status_reason.like("SOURCE SILENT%"))) or 0),
    }
