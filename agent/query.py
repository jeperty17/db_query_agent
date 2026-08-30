"""Query builder, execution, result shaping, and validation. See SPEC.md sections 10-12."""
import sqlite3
from datetime import date

from agent.cameras import CAMERAS, resolve_camera
from agent.intent import Clarification, Extraction, Intent, OutOfRange, QueryResult, Refusal

SAMPLE_CAP = 50
_SELECT = "SELECT frame_id, datetime, camera FROM frames"
_DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


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

    sql = _SELECT
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return sql + " ORDER BY datetime", params


def connect(db_path: str = "frames.db") -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def dataset_bounds(conn: sqlite3.Connection) -> tuple[date, date]:
    min_d, max_d = conn.execute("SELECT MIN(frame_date), MAX(frame_date) FROM frames").fetchone()
    return date.fromisoformat(min_d), date.fromisoformat(max_d)


def run_query(conn: sqlite3.Connection, intent: Intent) -> QueryResult:
    sql, params = build_query(intent)
    where = sql[len(_SELECT):-len(" ORDER BY datetime")]  # "" or " WHERE ..."
    total = conn.execute("SELECT COUNT(*) FROM frames" + where, params).fetchone()[0]
    rows = conn.execute(sql, params).fetchmany(SAMPLE_CAP)

    notes = []
    if total == 0:
        notes.append("No frames match those filters.")
    elif total > len(rows):
        notes.append(f"Showing the first {len(rows)} of {total:,}.")

    if intent.date_to:
        _, max_d = dataset_bounds(conn)
        if intent.date_to > max_d:
            notes.append(f"Data only goes up to {max_d:%d %b %Y}; the requested range extends beyond that.")

    return QueryResult(intent=intent, total=total, rows=rows, notes=notes)


def resolve_intent(
    extraction: Extraction, bounds: tuple[date, date]
) -> Intent | Clarification | Refusal | OutOfRange:
    """Validation: SPEC.md section 10. Turns a raw model Extraction into a
    validated Intent, or into the Clarification/Refusal/OutOfRange that
    validation itself produces. Dates and times are already resolved by the
    model; nothing here interprets a relative expression.
    """
    if extraction.action == "refuse":
        return Refusal(message=extraction.message or "This system only queries CCTV frame records.")
    if extraction.action == "clarify":
        return Clarification(question=extraction.message or "Could you clarify your request?")

    cameras = []
    for phrase in extraction.camera_phrases:
        resolved = resolve_camera(phrase)
        if resolved is None or resolved not in CAMERAS:  # A21: hallucinated value never reaches the query
            return Clarification(question=f"Which camera did you mean by \"{phrase}\"?")
        cameras.append(resolved)

    date_from, date_to = extraction.date_from, extraction.date_to
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from  # a backwards range is a user error with an obvious fix

    intent = Intent(
        camera=cameras, date_from=date_from, date_to=date_to,
        time_from=extraction.time_from, time_to=extraction.time_to,
        days_of_week=extraction.days_of_week,
    )

    min_d, max_d = bounds
    entirely_before = date_to is not None and date_to < min_d
    entirely_after = date_from is not None and date_from > max_d
    if entirely_before or entirely_after:
        return OutOfRange(intent=intent, requested=(date_from, date_to), available=(min_d, max_d))

    return intent


def _format_date_range(date_from: date | None, date_to: date | None) -> str:
    if not date_from and not date_to:
        return ""
    if date_from and not date_to:
        return f"from {date_from.day} {date_from:%b %Y}"
    if date_to and not date_from:
        return f"up to {date_to.day} {date_to:%b %Y}"
    if date_from == date_to:
        return f"{date_from.day} {date_from:%b %Y}"
    if (date_from.year, date_from.month) == (date_to.year, date_to.month):
        return f"{date_from.day}-{date_to.day} {date_to:%b %Y}"
    if date_from.year == date_to.year:
        return f"{date_from.day} {date_from:%b}-{date_to.day} {date_to:%b %Y}"
    return f"{date_from.day} {date_from:%b %Y} - {date_to.day} {date_to:%b %Y}"


def _format_days(days_of_week: list[int]) -> str:
    days = sorted(days_of_week)
    if days == [5, 6]:
        return "Weekends"
    if days == [0, 1, 2, 3, 4]:
        return "Weekdays"
    if len(days) == 1:
        return f"{_DOW_NAMES[days[0]]}s only"
    return " and ".join(f"{_DOW_NAMES[d]}s" for d in days)


def format_summary(result: QueryResult) -> str:
    intent = result.intent
    parts = [f"{result.total:,} frames"]
    if intent.camera:
        parts.append(", ".join(intent.camera))
    date_part = _format_date_range(intent.date_from, intent.date_to)
    if date_part:
        parts.append(date_part)
    if intent.time_from and intent.time_to:
        parts.append(f"{intent.time_from:%H:%M}-{intent.time_to:%H:%M}")
    if intent.days_of_week:
        parts.append(_format_days(intent.days_of_week))
    line = " | ".join(parts)
    if result.notes:
        line += "\n" + "\n".join(result.notes)
    return line
