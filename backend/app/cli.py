"""UK-ETDI command line.

    python -m app.cli health
    python -m app.cli pipeline [--dry-run] [--no-notify] [--sources a,b]
    python -m app.cli collect --source venue_pages [--city Leeds] [--category sports] [--dry-run]
    python -m app.cli coverage
    python -m app.cli sources
    python -m app.cli report [--send]            # daily digest (section 57 format); --send pushes via configured providers
    python -m app.cli events [--days 7] [--city X] [--category Y] [--min-score N] [--limit 50]
    python -m app.cli bookings import FILE | correlate | status

`collect` runs collectors only (no persistence unless --persist) and prints per-source counters.
`pipeline --dry-run` runs collection + validation and reports what *would* be persisted.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date

from app.core.logging import get_logger, setup_logging

log = get_logger("cli")


def _json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_health(args) -> int:
    from sqlalchemy import func, select

    from app.db.database import init_db, session_scope
    from app.db.models import Event, PipelineRun, Source

    init_db()
    with session_scope() as db:
        last = db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)).first()
        sources = db.scalars(select(Source).order_by(Source.priority.desc())).all()
        out = {
            "database": "HEALTHY",
            "events": db.scalar(select(func.count(Event.id))),
            "future_events": db.scalar(select(func.count(Event.id)).where(Event.date_start >= date.today())),
            "last_pipeline_run": None if not last else {"id": last.id, "status": last.status, "started_at": last.started_at, "duration_seconds": last.duration_seconds},
            "sources": [{"key": s.key, "enabled": s.enabled, "status": s.status, "last_events": s.last_events_collected, "last_success_at": s.last_success_at,
                         "error": (s.last_error or "")[:120] or None} for s in sources],
        }
    _json(out)
    return 0


def cmd_sources(args) -> int:
    from app.collectors.registry import COLLECTORS
    from app.core.config import sources_config

    rows = []
    for key, cfg in sorted(sources_config().items(), key=lambda kv: -kv[1].get("priority", 0)):
        cls = COLLECTORS.get(key)
        rows.append({"key": key, "type": cfg.get("type"), "priority": cfg.get("priority"), "enabled": cfg.get("enabled", True),
                     "requires_key": cfg.get("requires_key"), "collector": cls.__name__ if cls else None,
                     "source_confidence": getattr(cls, "source_confidence", None) if cls else None})
    _json(rows)
    return 0


def cmd_collect(args) -> int:
    from app.collectors.registry import CATEGORY_SOURCES, build_collectors

    only = [s.strip() for s in args.source.split(",")] if args.source else None
    if args.category:
        cat_sources = CATEGORY_SOURCES.get(args.category.lower())
        if cat_sources is None:
            print(f"unknown category {args.category}; known: {sorted(CATEGORY_SOURCES)}", file=sys.stderr)
            return 2
        only = [s for s in (only or cat_sources) if s in cat_sources]
    filters = {k: v for k, v in (("city", args.city), ("category", args.category), ("sport", args.sport)) if v}
    collectors = build_collectors(only, filters)
    if not collectors:
        print("no collectors matched", file=sys.stderr)
        return 2
    all_events = []
    summary = []
    for col in collectors:
        res = col.run()
        cats = Counter((e.category_hint or "").split(" ")[0] for e in res.events)
        cities = Counter(e.city_name for e in res.events)
        summary.append({
            "source": col.name, "status": res.status, "events": len(res.events), "endpoints_attempted": res.endpoints_attempted,
            "endpoints_ok": res.endpoints_ok, "blocked": res.blocked[:10], "warnings": res.warnings[:10], "error": res.error,
            "response_ms": res.response_ms, "top_categories": cats.most_common(5), "top_cities": cities.most_common(8),
        })
        all_events.extend(res.events)
    _json(summary)
    if args.show:
        for e in all_events[: args.show]:
            print(f"  {e.date_start} {e.time_start or '--:--'}  {e.title[:60]:<60} | {e.venue_name or '-'} | {e.city_name or '-'} | {e.status}")
    if args.persist:
        from app.orchestration.jobs import job_migrate, job_pipeline
        job_migrate()
        rid = job_pipeline(trigger="cli", only=[c.name for c in collectors], notify=False)
        print(f"persisted via pipeline run {rid}")
    return 0


def cmd_pipeline(args) -> int:
    from app.orchestration.jobs import job_migrate, job_pipeline

    only = [s.strip() for s in args.sources.split(",")] if args.sources else None
    if args.dry_run:
        from app.collectors.registry import build_collectors
        from app.processors.validation import validate

        collectors = build_collectors(only)
        out = []
        for col in collectors:
            res = col.run()
            checks = [validate(ev) for ev in res.events]
            valid = sum(1 for ok, _ in checks if ok)
            reasons = Counter(pr for ok, probs in checks if not ok for pr in probs)
            out.append({"source": col.name, "status": res.status, "collected": len(res.events), "valid": valid, "rejected": len(checks) - valid,
                        "rejection_reasons": dict(reasons.most_common(5)), "error": res.error})
        _json({"dry_run": True, "sources": out, "would_persist": sum(o["valid"] for o in out)})
        return 0
    job_migrate()
    rid = job_pipeline(trigger=args.trigger, only=only, notify=not args.no_notify)
    print(f"pipeline run id: {rid}")
    return 0


def cmd_coverage(args) -> int:
    from app.db.database import init_db, session_scope
    from app.intelligence.coverage import coverage_report

    init_db()
    with session_scope() as db:
        _json(coverage_report(db))
    return 0


def cmd_report(args) -> int:
    from app.db.database import SessionLocal, init_db
    from app.orchestration.reports import build_daily_report, format_daily_digest
    init_db()
    with SessionLocal() as db:
        report = build_daily_report(db)
        text = format_daily_digest(report)
        if args.json:
            _json(report); return 0
        print(text)
        if args.send:
            from app.providers import get_notification_providers
            for p in get_notification_providers():
                ok, msg = p.send("daily_digest", text) if p.is_configured() else (False, "not_configured")
                print(f"[{p.key}] {'sent' if ok else 'not sent'}: {msg}")
    return 0


def cmd_events(args) -> int:
    from datetime import timedelta
    from sqlalchemy import select
    from app.db.database import SessionLocal, init_db
    from app.db.models import Event
    init_db()
    today = date.today()
    with SessionLocal() as db:
        stmt = select(Event).where(Event.date_start >= today, Event.date_start <= today + timedelta(days=args.days))
        if args.city:
            stmt = stmt.where(Event.city_name_raw.ilike(f"%{args.city}%"))
        if args.category:
            stmt = stmt.where(Event.category == args.category)
        if args.min_score:
            stmt = stmt.where(Event.opportunity_score >= args.min_score)
        rows = db.scalars(stmt.order_by(Event.opportunity_score.desc(), Event.date_start).limit(args.limit)).all()
        if args.json:
            _json([{"id": e.id, "title": e.title, "date": e.date_start.isoformat(), "time": e.time_start, "venue": e.venue_name_raw, "city": e.city_name_raw,
                    "category": e.category, "score": e.opportunity_score, "demand": e.demand_level, "quality": e.quality_level, "status": e.status} for e in rows])
            return 0
        print(f"{'ID':>6}  {'Date':10} {'Time':5} {'Score':5} {'Demand':9} {'Q':6} {'Title':50} {'Venue':30} City")
        for e in rows:
            print(f"{e.id:>6}  {e.date_start.strftime('%d/%m/%Y'):10} {(e.time_start or 'TBC'):5} {e.opportunity_score or 0:>5} {(e.demand_level or ''):9} {(e.quality_level or ''):6} "
                  f"{(e.title or '')[:50]:50} {(e.venue_name_raw or '')[:30]:30} {e.city_name_raw or ''}")
        print(f"\n{len(rows)} events (next {args.days} days). Scores and demand levels are MODELLED.")
    return 0


def cmd_bookings(args) -> int:
    from app.db.database import SessionLocal, init_db
    from app.bookings import correlate, features, ingest
    init_db()
    with SessionLocal() as db:
        if args.action == "import":
            if not args.file:
                print("usage: bookings import FILE.(csv|json|xlsx)"); return 2
            _json(ingest.ingest(db, ingest.read_path(args.file), source_label=args.file))
        elif args.action == "correlate":
            st = correlate.correlate(db)
            st["features"] = features.refresh_features(db)
            _json(st)
        else:
            from sqlalchemy import func, select
            from app.db.models import EventBookingCorrelation, TaxiBooking
            mode, info = features.forecast_mode(db)
            _json({"bookings": db.scalar(select(func.count(TaxiBooking.id))), "correlations": db.scalar(select(func.count(EventBookingCorrelation.id))),
                   "model_mode": mode, **info})
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    p = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health").set_defaults(fn=cmd_health)
    sub.add_parser("sources").set_defaults(fn=cmd_sources)
    sub.add_parser("coverage").set_defaults(fn=cmd_coverage)
    c = sub.add_parser("collect")
    c.add_argument("--source"); c.add_argument("--city"); c.add_argument("--category"); c.add_argument("--sport")
    c.add_argument("--show", type=int, default=0, help="print first N events")
    c.add_argument("--persist", action="store_true", help="run the full pipeline restricted to the matched sources")
    c.add_argument("--dry-run", action="store_true", help="(default behaviour) collect only, do not persist")
    c.set_defaults(fn=cmd_collect)
    pl = sub.add_parser("pipeline")
    pl.add_argument("--dry-run", action="store_true"); pl.add_argument("--no-notify", action="store_true")
    pl.add_argument("--sources"); pl.add_argument("--trigger", default="cli")
    pl.set_defaults(fn=cmd_pipeline)
    rp = sub.add_parser("report"); rp.add_argument("--send", action="store_true"); rp.add_argument("--json", action="store_true"); rp.set_defaults(fn=cmd_report)
    ev = sub.add_parser("events"); ev.add_argument("--days", type=int, default=7); ev.add_argument("--city"); ev.add_argument("--category")
    ev.add_argument("--min-score", type=int, default=0); ev.add_argument("--limit", type=int, default=50); ev.add_argument("--json", action="store_true"); ev.set_defaults(fn=cmd_events)
    bk = sub.add_parser("bookings"); bk.add_argument("action", choices=["import", "correlate", "status"]); bk.add_argument("file", nargs="?"); bk.set_defaults(fn=cmd_bookings)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
