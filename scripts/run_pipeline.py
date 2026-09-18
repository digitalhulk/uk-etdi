#!/usr/bin/env python3
"""CLI: python scripts/run_pipeline.py [--sources a,b] [--no-notify] [--trigger scheduled]"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.orchestration.jobs import job_migrate, job_pipeline, job_report  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--sources"); p.add_argument("--no-notify", action="store_true"); p.add_argument("--trigger", default="cli")
p.add_argument("--report", action="store_true", help="print daily report JSON after run")
a = p.parse_args()
job_migrate()
rid = job_pipeline(trigger=a.trigger, only=a.sources.split(",") if a.sources else None, notify=not a.no_notify)
print(f"pipeline run id: {rid}")
if a.report:
    print(json.dumps(job_report(), indent=2, default=str))
