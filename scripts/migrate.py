#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.orchestration.jobs import job_migrate  # noqa: E402
job_migrate(); print("migrations + seed complete")
