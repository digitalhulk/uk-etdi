from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings, scoring_config, sources_config
from app.core.security import require_admin
from app.db.models import Setting
from app.schemas.api import ok

router = APIRouter(tags=["settings"])

DEFAULTS: dict[str, Any] = {
    "service_area_cities": None, "home_city": None, "priority_categories": ["music", "sports", "festival"],
    "score_thresholds": None, "notifications": {"telegram_daily_digest": True, "digest_time_local": "07:00"},
    "collection_frequency": "daily",
    "service_area": {"primary_city": "", "radius_miles": 25, "priority_postcodes": [], "airports": [], "stations": [], "venues": [], "priority_cities": []},
}


@router.get("/settings")
def get_settings_view(db: Session = Depends(get_db)):
    s = get_settings()
    stored = {r.key: r.value for r in db.scalars(select(Setting)).all()}
    view = {**DEFAULTS, **stored}
    view["service_area_cities"] = stored.get("service_area_cities") or s.service_area
    view["home_city"] = stored.get("home_city") or s.home_city
    sa = {**DEFAULTS["service_area"], **(stored.get("service_area") or {})}
    sa["primary_city"] = sa["primary_city"] or view["home_city"]
    sa["priority_cities"] = sa["priority_cities"] or list(view["service_area_cities"])
    view["service_area"] = sa
    view["score_thresholds"] = stored.get("score_thresholds") or scoring_config().get("demand_levels")
    view["scoring_weights"] = scoring_config().get("weights")
    view["sources"] = {k: {"enabled": v.get("enabled"), "type": v.get("type"), "priority": v.get("priority"), "requires_key": v.get("requires_key")} for k, v in sources_config().items()}
    view["integrations"] = {  # never expose secrets — only configured flags
        "telegram": bool(s.telegram_bot_token and s.telegram_chat_id), "google_sheets": bool(s.google_sheets_webhook),
        "ticketmaster": bool(s.ticketmaster_api_key), "eventbrite": bool(s.eventbrite_api_key), "jambase": bool(s.jambase_api_key),
    }
    return ok(view)


class SettingBody(BaseModel):
    value: Any


SECRET_KEYS = {"telegram_bot_token", "telegram_chat_id", "google_sheets_webhook", "api_admin_token", "ticketmaster_api_key", "eventbrite_api_key", "jambase_api_key", "smtp_password"}
EDITABLE_KEYS = {"service_area_cities", "home_city", "priority_categories", "score_thresholds", "notifications", "collection_frequency", "service_area"}


@router.put("/settings", dependencies=[Depends(require_admin)])
def put_settings(body: dict[str, Any], db: Session = Depends(get_db)):
    """Bulk update of non-secret settings. Secrets live in env only and are rejected here."""
    from fastapi import HTTPException
    bad = [k for k in body if k in SECRET_KEYS or k not in EDITABLE_KEYS]
    if bad:
        raise HTTPException(400, detail={"code": "SETTING_NOT_EDITABLE", "message": f"Not editable via API: {', '.join(bad)}"})
    for key, value in body.items():
        row = db.get(Setting, key)
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()
    return get_settings_view(db)


@router.put("/settings/{key}", dependencies=[Depends(require_admin)])
def put_setting(key: str, body: SettingBody, db: Session = Depends(get_db)):
    if key in SECRET_KEYS or key not in EDITABLE_KEYS:
        from fastapi import HTTPException
        raise HTTPException(400, detail={"code": "SETTING_NOT_EDITABLE", "message": f"Not editable via API: {key}"})
    row = db.get(Setting, key)
    if row:
        row.value = body.value
    else:
        db.add(Setting(key=key, value=body.value))
    db.commit()
    return ok({"key": key, "value": body.value})
