from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Meta(BaseModel):
    page: int = 1
    page_size: int = 50
    total: int = 0


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    meta: Meta | dict[str, Any] | None = None


def ok(data: Any, meta: dict | None = None) -> dict:
    out: dict[str, Any] = {"success": True, "data": data}
    if meta is not None:
        out["meta"] = meta
    return out


def fail(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}
