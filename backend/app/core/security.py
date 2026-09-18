"""Minimal admin protection. If API_ADMIN_TOKEN is unset, admin endpoints are open (local dev)."""
from fastapi import Header, HTTPException

from .config import get_settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    token = get_settings().api_admin_token
    if token and x_admin_token != token:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Admin token required"})
