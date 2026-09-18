"""Daily report builder + Telegram digest formatter. All numbers come from the database."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ErrorLog, Event, EventChange, MarketingAction, PipelineRun, Source, utcnow

ACTIVE = ("SCHEDULED", "RESCHEDULED", "CONFIRMED", "SOLD_OUT")


def _count(db: Session, *conds) -> int:
    return db.scalar(select(func.count(Event.id)).where(*conds)) or 0


def summary_counts(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    week = today + timedelta(days=7)
    since = today - timedelta(days=1)
    upcoming = (Event.date_start >= today, Event.date_start <= week, Event.status.in_(ACTIVE))
    return {
        "date": today.isoformat(),
        "events_today": _count(db, Event.date_start <= today, func.coalesce(Event.date_end, Event.date_start) >= today, Event.status.in_(ACTIVE)),
        "events_tomorrow": _count(db, Event.date_start <= tomorrow, func.coalesce(Event.date_end, Event.date_start) >= tomorrow, Event.status.in_(ACTIVE)),
        "events_next_7_days": _count(db, *upcoming),
        "events_next_30_days": _count(db, Event.date_start >= today, Event.date_start <= today + timedelta(days=30), Event.status.in_(ACTIVE)),
        "high": _count(db, *upcoming, Event.demand_level == "HIGH"),
        "very_high": _count(db, *upcoming, Event.demand_level == "VERY_HIGH"),
        "medium": _count(db, *upcoming, Event.demand_level == "MEDIUM"),
        "next_scheduled_run": _next_cron_run(),
        "data_freshness": _data_freshness(db),
        "new_events": db.scalar(select(func.count(func.distinct(EventChange.event_id))).where(EventChange.change_type == "NEW", EventChange.detected_at >= since)) or 0,
        "changed_events": db.scalar(select(func.count(func.distinct(EventChange.event_id))).where(EventChange.change_type.notin_(["NEW", "CANCELLED"]), EventChange.detected_at >= since)) or 0,
        "cancelled_events": db.scalar(select(func.count(func.distinct(EventChange.event_id))).where(EventChange.change_type == "CANCELLED", EventChange.detected_at >= since)) or 0,
        "sources_total": db.scalar(select(func.count(Source.id)).where(Source.enabled.is_(True))) or 0,
        "sources_healthy": db.scalar(select(func.count(Source.id)).where(Source.status.in_(["HEALTHY", "DEGRADED", "EMPTY"]))) or 0,
        "sources_empty": db.scalar(select(func.count(Source.id)).where(Source.status == "EMPTY")) or 0,
        "sources_blocked": db.scalar(select(func.count(Source.id)).where(Source.status == "BLOCKED")) or 0,
        "source_regressions": [e.message for e in db.scalars(select(ErrorLog).where(ErrorLog.pipeline_run_id == db.scalar(select(func.max(PipelineRun.id))), ErrorLog.message.like("regression:%"))).all()],
        "open_actions": db.scalar(select(func.count(MarketingAction.id)).join(Event).where(MarketingAction.status.in_(["NEW", "PLANNED", "SCHEDULED", "IN_PROGRESS"]), Event.date_start >= today, Event.date_start <= today + timedelta(days=14))) or 0,
    }


def top_events(db: Session, today: date | None = None, days: int = 7, limit: int = 5) -> list[Event]:
    today = today or date.today()
    return db.scalars(select(Event).where(Event.date_start >= today, Event.date_start <= today + timedelta(days=days), Event.status.in_(ACTIVE))
                      .order_by(Event.opportunity_score.desc(), Event.date_start.asc()).limit(limit)).all()


def event_brief(e: Event) -> dict:
    return {
        "id": e.id, "title": e.title, "date": e.date_start.isoformat(), "time": e.time_start, "venue": e.venue.name if e.venue else e.venue_name_raw,
        "city": e.city.name if e.city else e.city_name_raw, "score": e.opportunity_score, "demand_level": e.demand_level,
        "category": e.category, "marketing_priority": e.marketing_priority,
        "top_action": next((a.title for a in e.marketing_actions if a.status == "NEW"), None),
        "post_window": (e.demand_windows or {}).get("post_event_window"),
        "quality_level": e.quality_level, "source_confidence": e.source_confidence, "status": e.status,
        "capacity": e.venue.capacity if e.venue else None,
    }


def service_area_top(db: Session, today: date, days: int = 7, limit: int = 5) -> list[Event]:
    """Top events inside the configured service area (Settings table → env fallback), HIGH/MEDIUM quality only."""
    from app.core.service_area import load_service_area
    from app.db.models import City
    sa = load_service_area(db)
    if not sa["normalized"]:
        return []
    return db.scalars(select(Event).join(City, City.id == Event.city_id).where(Event.date_start >= today, Event.date_start <= today + timedelta(days=days),
                                                                             Event.status.in_(ACTIVE), City.normalized_name.in_(list(sa["normalized"])),
                                                                             Event.quality_level.in_(["HIGH", "MEDIUM"]))
                      .order_by(Event.opportunity_score.desc(), Event.date_start.asc()).limit(limit)).all()


def build_daily_report(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    from app.core.service_area import load_service_area
    from app.intelligence.coverage import horizon_counts
    sa = load_service_area(db)
    silent = db.scalar(select(func.count(Event.id)).where(Event.date_start >= today, Event.status_reason.like("SOURCE SILENT%"))) or 0
    from app.db.models import PipelineRun
    week = today + timedelta(days=7)
    cats = dict(db.execute(select(Event.category, func.count(Event.id)).where(Event.date_start >= today, Event.date_start <= week, Event.status.in_(ACTIVE)).group_by(Event.category)).all())
    last = db.scalars(select(PipelineRun).where(PipelineRun.status != "RUNNING").order_by(PipelineRun.id.desc()).limit(1)).first()
    return {"generated_for": today.isoformat(), "summary": {**summary_counts(db, today), "horizons": horizon_counts(db, today), "source_silent_events": silent},
            "by_category_7d": cats, "pipeline_status": last.status if last else "UNKNOWN",
            "service_area": {"cities": sa["cities"], "source": sa["source"], "top": [event_brief(e) for e in service_area_top(db, today)]},
            "top_opportunities": [event_brief(e) for e in top_events(db, today)],
            "today": [event_brief(e) for e in db.scalars(select(Event).where(Event.date_start == today, Event.status.in_(ACTIVE)).order_by(Event.opportunity_score.desc()).limit(20)).all()],
            "disclaimer": "Scores and demand windows are modelled estimates, not observed taxi demand."}


def _fmt_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%a %d %b")


def _event_lines(t: dict, idx: int | None = None) -> list[str]:
    head = f"{idx}. {t['title']}" if idx else t["title"]
    loc = ", ".join(x for x in (t.get("venue"), t.get("city")) if x)
    lines = [head, f"   📍 {loc}" if loc else "   📍 venue TBC",
             f"   📆 {_fmt_date(t['date'])}  🕐 {t['time'] or 'TBC'}   🔥 {t['score']} ({(t.get('demand_level') or '').replace('_', ' ')})",
             f"   ✔ quality {t.get('quality_level') or 'n/a'} · source {t.get('source_confidence') or 'n/a'}" + (f" · {t['status']}" if t.get("status") not in (None, "SCHEDULED") else "")]
    if t.get("post_window"):
        lines.append(f"   🚕 modelled departure window {t['post_window']['start']}–{t['post_window']['end']}")
    if t.get("top_action"):
        lines.append(f"   ▶ {t['top_action']}")
    return lines


def format_daily_digest(report: dict) -> str:
    """Telegram digest v2 in the section-31 layout. No-spam rule (§32): when nothing clears the bar, a short status message is sent."""
    s = report["summary"]
    d = date.fromisoformat(report["generated_for"])
    bar = "━━━━━━━━━━━━"
    top = (report.get("service_area", {}).get("top") or []) or report.get("top_opportunities", [])
    top = [t for t in top if (t.get("demand_level") in ("VERY_HIGH", "HIGH", "MEDIUM")) and (t.get("quality_level") in (None, "HIGH", "MEDIUM"))][:5]
    cats = report.get("by_category_7d", {})
    lines = ["🚕 UK TAXI INTELLIGENCE", "", d.strftime("%A %d %B %Y"), "",
             f"🔥 VERY HIGH OPPORTUNITIES\n{s['very_high']}", "", f"🔴 HIGH\n{s['high']}", "", f"🟡 MEDIUM\n{s['medium']}", "", bar, ""]
    if not top and s["very_high"] + s["high"] == 0:
        lines += ["No high-priority taxi opportunities detected today.", "", bar, ""]
    else:
        lines.append("🔥 TOP 5")
        lines.append("")
        for i, t in enumerate(top, 1):
            loc = ", ".join(x for x in (t.get("venue"), t.get("city")) if x) or "venue TBC"
            why = f"{(t.get('demand_level') or '').replace('_', ' ').title()} modelled demand"
            if t.get("capacity"):
                why += f" · capacity {t['capacity']:,}"
            if t.get("post_window"):
                why += f" · departures {t['post_window']['start']}–{t['post_window']['end']} (modelled)"
            why += f" · quality {t.get('quality_level') or 'n/a'} / {t.get('source_confidence') or 'n/a'}"
            lines += [f"{i}.", t["title"], loc, f"{_fmt_date(t['date'])} {t['time'] or 'TBC'}", f"Score {t['score']}", why, "",
                      f"Recommended action: {t['top_action'] or 'none (gate closed)'}", ""]
        lines += [bar, ""]
    lines += ["🚨 EVENT CHANGES", "", f"New:\n{s['new_events']}", "", f"Updated:\n{s['changed_events']}", "", f"Cancelled:\n{s['cancelled_events']}", "", bar, "",
              f"🎓 EDUCATION\n{cats.get('education', 0)} events", "", f"🏟 SPORTS\n{cats.get('sports', 0)} events", "", f"🎵 MUSIC\n{cats.get('music', 0)} events", "", bar, "",
              "SYSTEM", "", f"Sources:\n{s['sources_healthy']}/{s['sources_total']} healthy", "", f"Pipeline:\n{report.get('pipeline_status', 'UNKNOWN')}"]
    if s.get("source_silent_events"):
        lines += ["", f"⚠ {s['source_silent_events']} events SOURCE SILENT"]
    if s.get("sources_blocked"):
        lines += ["", f"⛔ {s['sources_blocked']} source(s) BLOCKED (not retried)"]
    for msg in s.get("source_regressions") or []:
        lines += ["", f"⚠ Source {msg}"]
    lines += ["", "ℹ️ Scores/windows are MODELLED, not observed demand."]
    text = "\n".join(lines)
    return text if len(text) <= 4000 else text[:3990] + "\n…"


def _next_cron_run() -> str:
    """Next GitHub Actions daily cron (06:00 UTC default; PIPELINE_CRON_HOUR_UTC overrides)."""
    import os
    from datetime import datetime as _dt, timezone
    hour = int(os.getenv("PIPELINE_CRON_HOUR_UTC", "6"))
    now = _dt.now(timezone.utc)
    nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return nxt.isoformat()


def _data_freshness(db) -> dict:
    """Hours since the last successful pipeline run + average freshness_score of upcoming events."""
    last_ok = db.scalar(select(PipelineRun).where(PipelineRun.status.in_(("SUCCESS", "PARTIAL"))).order_by(PipelineRun.id.desc()).limit(1))
    hours = round((utcnow() - last_ok.completed_at).total_seconds() / 3600, 1) if last_ok and last_ok.completed_at else None
    avg = db.scalar(select(func.avg(Event.freshness_score)).where(Event.date_start >= date.today()))
    label = "FRESH" if hours is not None and hours <= 26 else ("STALE" if hours is not None else "UNKNOWN")
    return {"hours_since_last_success": hours, "avg_freshness_score": round(float(avg), 1) if avg is not None else None, "label": label}
