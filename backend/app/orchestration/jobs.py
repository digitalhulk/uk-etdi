"""Named jobs runnable from CLI/GitHub Actions/scheduler."""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.database import init_db, session_scope
from app.db.repositories.seed import seed_reference_data

log = get_logger("jobs")


def job_migrate() -> None:
    init_db()
    with session_scope() as db:
        counts = seed_reference_data(db)
    log.info("migrated + seeded: %s", counts)


def job_pipeline(trigger: str = "scheduled", only: list[str] | None = None, notify: bool = True) -> int:
    from app.orchestration.pipeline import run_pipeline
    init_db()
    with session_scope() as db:
        run = run_pipeline(db, trigger=trigger, only_sources=only, notify=notify)
        return run.id


def job_rescore() -> None:
    from app.orchestration.pipeline import Pipeline
    init_db()
    with session_scope() as db:
        p = Pipeline(db, trigger="rescore", notify=False)
        db.add(p.run); db.commit()
        p._intelligence()
        p.run.status = "SUCCESS"


def job_report() -> dict:
    from app.orchestration.reports import build_daily_report
    init_db()
    with session_scope() as db:
        return build_daily_report(db)
