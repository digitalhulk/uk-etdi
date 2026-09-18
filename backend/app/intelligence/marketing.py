"""Marketing intelligence: recommendation generator for high-value events. Outputs are suggestions, not guarantees.

Phase 2 gating (config/scoring.yaml → action_gating): an event only receives recommendations when ALL of
  * opportunity_score ≥ min_opportunity_score
  * quality_level ≥ min_quality_level (LOW-quality events never get automatic marketing)
  * status not CANCELLED/POSTPONED/COMPLETED
  * inside the configured service area (if require_service_area)
  * min_days_ahead ≤ days-until-event ≤ max_days_ahead
Every action records `reason` (the facts that opened the gate) and `recommended_date`.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.core.config import scoring_config
from app.db.models import Event

LEVEL_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def gate(event: Event, today: date | None = None) -> tuple[bool, list[str]]:
    """Returns (passes, reasons). Reasons explain either why it passed (facts) or the first failing gate."""
    from app.intelligence.taxi_opportunity import in_service_area

    g = scoring_config().get("action_gating", {}) or {}
    today = today or date.today()
    min_score = int(g.get("min_opportunity_score", 60))
    min_level = str(g.get("min_quality_level", "MEDIUM")).upper()
    days = (event.date_start - today).days
    if event.status in ("CANCELLED", "POSTPONED", "COMPLETED"):
        return False, [f"status {event.status}"]
    if (event.opportunity_score or 0) < min_score:
        return False, [f"opportunity score {event.opportunity_score} < {min_score}"]
    if LEVEL_RANK.get((event.quality_level or "LOW").upper(), 0) < LEVEL_RANK.get(min_level, 1):
        return False, [f"quality {event.quality_level or 'LOW'} below {min_level}"]
    if g.get("require_service_area", True) and not in_service_area(event):
        return False, ["outside service area"]
    if not (int(g.get("min_days_ahead", 0)) <= days <= int(g.get("max_days_ahead", 45))):
        return False, [f"{days} days ahead outside window"]
    facts = [f"opportunity score {event.opportunity_score} ≥ {min_score}", f"quality {event.quality_level} ({event.event_quality_score})",
             f"status {event.status}", f"{days} days ahead", "inside service area"]
    if event.venue and event.venue.capacity:
        facts.append(f"venue capacity {event.venue.capacity:,} ({event.venue.capacity_source or 'registry'})")
    return True, facts


def generate_marketing_actions(event: Event, today: date | None = None) -> list[dict]:
    g = scoring_config().get("action_gating", {}) or {}
    passes, facts = gate(event, today)
    if not passes:
        return []
    reason = "; ".join(facts)
    venue = event.venue.name if event.venue else (event.venue_name_raw or "the venue")
    city = event.city.name if event.city else (event.city_name_raw or "")
    prio = event.marketing_priority or "P3"
    d = event.date_start
    date_str = d.strftime("%a %d %b %Y")
    lead = (d - timedelta(days=7)).isoformat()
    day_before = (d - timedelta(days=1)).isoformat()
    slug = f"/taxi-{slugify(venue)}/"
    kw = f"taxi to {venue}"
    audience = f"Adults 18–55 within 25 km of {city or venue}, interests: {event.category}"
    actions = [
        {"action_type": "SEO", "priority": prio, "title": f"Optimise for “{kw}”", "suggested_keyword": kw, "suggested_channel": "Website/SEO",
         "description": f"Add an FAQ + fare guide block targeting '{kw}' and '{venue} taxi'. Mention {event.title} on {date_str}.",
         "recommended_time": f"Publish by {lead}", "recommended_date": lead, "suggested_audience": "Organic search"},
        {"action_type": "GOOGLE_ADS", "priority": prio, "title": f"Search campaign: “taxi near {venue}”", "suggested_keyword": f"taxi near {venue}",
         "suggested_channel": "Google Search", "description": f"Exact/phrase match on 'taxi near {venue}', '{venue} taxi', 'cab from {venue}'. Schedule ads {day_before} → event night.",
         "recommended_time": f"{day_before} to {d.isoformat()} 23:59", "recommended_date": day_before, "suggested_audience": f"Searchers within 15 km of {venue}"},
        {"action_type": "LANDING_PAGE", "priority": prio, "title": f"Landing page {slug}", "suggested_keyword": kw, "suggested_channel": "Website",
         "description": f"Create {slug} with pickup points, fixed fares to stations/hotels, and a booking CTA. Reuse for all {venue} events.",
         "recommended_time": f"Live by {lead}", "recommended_date": lead, "suggested_audience": "Paid + organic traffic"},
        {"action_type": "GBP_POST", "priority": prio, "title": f"Google Business Profile update for {event.title}", "suggested_channel": "Google Business Profile",
         "description": f"Post: 'Heading to {event.title} at {venue} on {date_str}? Book your ride in advance.'", "recommended_time": f"{day_before} 10:00",
         "recommended_date": day_before, "suggested_audience": "Local map-pack searchers", "suggested_keyword": f"{venue} taxi"},
        {"action_type": "SOCIAL_POST", "priority": prio, "title": f"Social post: {event.title}", "suggested_channel": "Instagram/Facebook/X",
         "description": f"'Heading home after {event.title}? Pre-book now and skip the queue at {venue}.' Post afternoon of event.",
         "recommended_time": f"{d.isoformat()} 14:00", "recommended_date": d.isoformat(), "suggested_audience": audience},
    ]
    if (event.opportunity_score or 0) >= 65:
        actions.append({"action_type": "META_ADS", "priority": prio, "title": f"Meta Ads: {event.title}", "suggested_channel": "Meta Ads",
                        "description": f"Geo-fenced awareness + conversion ads around {venue} on event day. Creative: 'Safe ride home from {venue}'.",
                        "recommended_time": f"{day_before} to {d.isoformat()}", "recommended_date": day_before, "suggested_audience": audience, "suggested_keyword": None})
        actions.append({"action_type": "WHATSAPP_CTA", "priority": prio, "title": "WhatsApp booking CTA", "suggested_channel": "WhatsApp",
                        "description": f"Broadcast to opted-in customers: 'Going to {event.title}? Reply BOOK for a fixed-price return.'",
                        "recommended_time": f"{day_before} 18:00", "recommended_date": day_before, "suggested_audience": "Opted-in customer list", "suggested_keyword": None})
    cap = event.venue.capacity if event.venue else None
    if cap and cap >= int(g.get("email_partnership_min_capacity", 15000)) and (event.opportunity_score or 0) >= int(g.get("email_partnership_min_score", 70)):
        two_weeks = (d - timedelta(days=14)).isoformat()
        actions.append({"action_type": "EMAIL", "priority": prio, "title": f"Email campaign: {event.title}", "suggested_channel": "Email",
                        "description": f"Send to past customers in {city or 'the area'}: fixed-price returns for {event.title} at {venue} ({date_str}). Include pre-booking link.",
                        "recommended_time": f"{lead} 09:00", "recommended_date": lead, "suggested_audience": "Existing customer list (opted-in)", "suggested_keyword": None})
        actions.append({"action_type": "PARTNERSHIP", "priority": prio, "title": f"Partnership outreach: {venue}", "suggested_channel": "Direct outreach",
                        "description": f"Approach {venue} operations / nearby hotels about an official pickup point or concierge referral for {event.title} "
                                       f"(capacity {cap:,}). Reusable for future events at this venue.",
                        "recommended_time": f"By {two_weeks}", "recommended_date": two_weeks, "suggested_audience": "Venue operations, hotel concierges", "suggested_keyword": None})
    for a in actions:
        a["reason"] = reason
    return actions[: int(g.get("max_actions_per_event", 8))]
