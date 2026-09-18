import os, tempfile, pathlib
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["GOOGLE_SHEETS_WEBHOOK"] = ""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def db_session():
    from app.db.database import init_db, session_scope
    from app.db.repositories.seed import seed_reference_data
    init_db()
    with session_scope() as db:
        seed_reference_data(db)
    with session_scope() as db:
        yield db


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c
