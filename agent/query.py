"""Query builder and read-only execution. See SPEC.md section 11."""
import sqlite3

from agent.intent import Intent


def build_query(intent: Intent) -> tuple[str, list]:
    clauses, params = [], []

    if intent.camera:
        placeholders = ",".join("?" * len(intent.camera))
        clauses.append(f"camera IN ({placeholders})")
        params.extend(intent.camera)

    if intent.date_from:
        clauses.append("frame_date >= ?")
        params.append(intent.date_from.isoformat())

    if intent.date_to:
        clauses.append("frame_date <= ?")
        params.append(intent.date_to.isoformat())

    if intent.time_from and intent.time_to:
        a = intent.time_from.strftime("%H:%M")
        b = intent.time_to.strftime("%H:%M")
        if intent.time_from <= intent.time_to:
            clauses.append("frame_time >= ? AND frame_time <= ?")
        else:
            clauses.append("(frame_time >= ? OR frame_time <= ?)")  # overnight
        params.extend([a, b])

    if intent.days_of_week:
        placeholders = ",".join("?" * len(intent.days_of_week))
        clauses.append(f"day_of_week IN ({placeholders})")
        params.extend(intent.days_of_week)

    sql = "SELECT frame_id, datetime, camera FROM frames"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return sql + " ORDER BY datetime", params


def connect(db_path: str = "frames.db") -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
