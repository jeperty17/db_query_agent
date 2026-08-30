"""Frozen clocks and the session-scoped database fixture. See SPEC.md section 15."""
import sqlite3
from datetime import date, datetime

import pytest

from setup_db import DB_PATH, generate

NOW_A = datetime(2026, 8, 30, 14, 30)   # Sunday
NOW_B = datetime(2026, 8, 19, 9, 0)     # Wednesday


@pytest.fixture(scope="session")
def db_conn():
    generate(date.today(), DB_PATH)  # idempotent; ensures the db exists and is current
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    yield conn
    conn.close()
