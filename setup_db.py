"""Generates frames.db: one row per camera every 5 minutes, 2026-01-01 through today.

Idempotent: rerunning appends only the days missing since the last run.
"""
import sqlite3
from datetime import date, datetime, timedelta

DB_PATH = "frames.db"
START_DATE = date(2026, 1, 1)

CAMERAS = ["PIE", "AYE", "ECP", "CTE", "TPE", "KPE", "SLE", "BKE", "KJE", "MCE"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    frame_id     INTEGER PRIMARY KEY,
    datetime     TEXT    NOT NULL,
    camera       TEXT    NOT NULL,
    frame_date   TEXT    NOT NULL,
    frame_time   TEXT    NOT NULL,
    day_of_week  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_frames_lookup ON frames(camera, frame_date, frame_time);
CREATE INDEX IF NOT EXISTS idx_frames_dow    ON frames(day_of_week);
"""


def _rows_for_day(day: date) -> list[tuple]:
    rows = []
    midnight = datetime(day.year, day.month, day.day)
    dow = day.weekday()  # 0=Monday, matches Intent.days_of_week convention
    for minute in range(0, 24 * 60, 5):
        dt = midnight + timedelta(minutes=minute)
        for camera in CAMERAS:
            rows.append((dt.isoformat(), camera, day.isoformat(), dt.strftime("%H:%M"), dow))
    return rows


def generate(today: date, db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    max_date = conn.execute("SELECT MAX(frame_date) FROM frames").fetchone()[0]
    start = date.fromisoformat(max_date) + timedelta(days=1) if max_date else START_DATE

    rows = []
    d = start
    while d <= today:
        rows.extend(_rows_for_day(d))
        d += timedelta(days=1)

    if rows:
        conn.executemany(
            "INSERT INTO frames (datetime, camera, frame_date, frame_time, day_of_week) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    total, min_date, max_date = conn.execute(
        "SELECT COUNT(*), MIN(frame_date), MAX(frame_date) FROM frames"
    ).fetchone()
    print(f"{total} rows, {min_date} to {max_date}")
    conn.close()


if __name__ == "__main__":
    generate(date.today())
