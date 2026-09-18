from fastapi import APIRouter

from . import bookings, cities, coverage, dashboard, events, exports, health, opportunities, pipeline, settings, sources, venues

api_router = APIRouter(prefix="/api")
for m in (events, opportunities, dashboard, sources, venues, cities, health, settings, pipeline, coverage, exports, bookings):
    api_router.include_router(m.router)
