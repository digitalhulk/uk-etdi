"""UK-ETDI FastAPI application. Serves the REST API and the static dashboard (frontend/)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router
from app.core.config import ROOT_DIR, get_settings
from app.core.logging import get_logger
from app.db.database import init_db, session_scope
from app.db.repositories.seed import seed_reference_data
from app.orchestration.scheduler import start_scheduler, stop_scheduler
from app.schemas.api import fail

log = get_logger("main")
FRONTEND_DIR = ROOT_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as db:
        seed_reference_data(db)
    start_scheduler()
    log.info("UK-ETDI ready (%s)", get_settings().app_env)
    yield
    stop_scheduler()


app = FastAPI(title="UK Event → Taxi Demand Intelligence Platform", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router)


@app.exception_handler(HTTPException)
async def http_exc(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=fail(detail.get("code", "HTTP_ERROR"), detail.get("message", "")))


@app.exception_handler(Exception)
async def any_exc(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content=fail("INTERNAL_ERROR", str(exc)[:200]))


if FRONTEND_DIR.exists():
    for sub in ("public", "lib", "components", "app"):
        app.mount(f"/{sub}", StaticFiles(directory=FRONTEND_DIR / sub), name=sub)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(FRONTEND_DIR / "app" / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content=fail("NOT_FOUND", "Unknown API route"))
        return FileResponse(FRONTEND_DIR / "app" / "index.html")
