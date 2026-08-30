"""Frozen clocks and the session-scoped database fixture. See SPEC.md section 15."""
import sqlite3
from datetime import datetime

import pytest

from setup_db import generate

NOW_A = datetime(2026, 8, 30, 14, 30)   # Sunday
NOW_B = datetime(2026, 8, 19, 9, 0)     # Wednesday

TEST_DB_PATH = "test_frames.db"


@pytest.fixture(scope="session")
def db_conn():
    # Pinned to NOW_A's date, not date.today(): the matrix's expected row
    # counts, dataset-coverage notes, and OutOfRange bounds all assume "today"
    # is 2026-08-30. Using the real wall clock here would silently append a
    # new day whenever tests run after that date and break every one of them.
    # A separate file from the production frames.db so running tests never
    # mutates the db the CLI actually appends to.
    generate(NOW_A.date(), TEST_DB_PATH)
    conn = sqlite3.connect(f"file:{TEST_DB_PATH}?mode=ro", uri=True)
    yield conn
    conn.close()
