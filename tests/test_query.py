"""Tests that requests turn into correct, safe database queries."""
from datetime import date, time

from agent.intent import Clarification, Extraction, Intent, OutOfRange, QueryResult, Refusal
from agent.query import build_query, format_summary, resolve_intent, run_query
from tests.conftest import BOUNDS


def test_no_filters():
    sql, params = build_query(Intent())
    assert sql == "SELECT frame_id, datetime, camera FROM frames ORDER BY datetime"
    assert params == []


def test_camera_clause():
    sql, params = build_query(Intent(camera=["CTE", "PIE"]))
    assert "camera IN (?,?)" in sql
    assert params == ["CTE", "PIE"]


def test_date_range_clause():
    sql, params = build_query(Intent(date_from=date(2026, 8, 1), date_to=date(2026, 8, 30)))
    assert "frame_date >= ?" in sql
    assert "frame_date <= ?" in sql
    assert params == ["2026-08-01", "2026-08-30"]


def test_time_range_normal():
    sql, params = build_query(Intent(time_from=time(8, 0), time_to=time(10, 0)))
    assert "frame_time >= ? AND frame_time <= ?" in sql
    assert params == ["08:00", "10:00"]


def test_time_range_overnight_uses_or_and_does_not_touch_date():
    sql, params = build_query(
        Intent(date_from=date(2026, 8, 30), date_to=date(2026, 8, 30), time_from=time(22, 0), time_to=time(6, 0))
    )
    assert "(frame_time >= ? OR frame_time <= ?)" in sql
    assert params == ["2026-08-30", "2026-08-30", "22:00", "06:00"]  # date_to unshifted


def test_days_of_week_clause():
    sql, params = build_query(Intent(days_of_week=[0, 4]))
    assert "day_of_week IN (?,?)" in sql
    assert params == [0, 4]


def test_whole_dataset_row_count_matches(db_conn):
    sql, params = build_query(Intent())
    rows = db_conn.execute(sql, params).fetchall()
    assert len(rows) == db_conn.execute("SELECT COUNT(*) FROM frames").fetchone()[0]


def test_C1_time_boundary_inclusive_both_ends(db_conn):
    intent = Intent(camera=["PIE"], date_from=date(2026, 8, 30), date_to=date(2026, 8, 30),
                     time_from=time(8, 0), time_to=time(10, 0))
    sql, params = build_query(intent)
    rows = db_conn.execute(sql, params).fetchall()
    assert len(rows) == 25  # 08:00..10:00 inclusive, 5-minute steps
    times = [r[1][11:16] for r in rows]
    assert times[0] == "08:00" and times[-1] == "10:00"


def test_C10_overnight_stays_within_each_day(db_conn):
    intent = Intent(camera=["PIE"], date_from=date(2026, 8, 30), date_to=date(2026, 8, 30),
                     time_from=time(22, 0), time_to=time(6, 0))
    sql, params = build_query(intent)
    rows = db_conn.execute(sql, params).fetchall()
    assert len(rows) == 97  # 22:00-23:55 (24) + 00:00-06:00 (73)
    assert all(r[1][:10] == "2026-08-30" for r in rows)


def test_C11_five_minute_boundary_zero_rows(db_conn):
    intent = Intent(camera=["PIE"], date_from=date(2026, 8, 30), date_to=date(2026, 8, 30),
                     time_from=time(10, 1), time_to=time(10, 3))
    sql, params = build_query(intent)
    assert db_conn.execute(sql, params).fetchall() == []


def test_D7_day_of_week_origin_matches_python_monday_zero(db_conn):
    # 2026-08-25 is a Tuesday, 2026-08-24 is a Monday.
    tuesday = Intent(days_of_week=[1], date_from=date(2026, 8, 25), date_to=date(2026, 8, 25))
    sql, params = build_query(tuesday)
    assert len(db_conn.execute(sql, params).fetchall()) == 2880  # 288 samples * 10 cameras

    monday = Intent(days_of_week=[1], date_from=date(2026, 8, 24), date_to=date(2026, 8, 24))
    sql, params = build_query(monday)
    assert db_conn.execute(sql, params).fetchall() == []


# --- Phase 5: result shaping and the summary line ---

def test_run_query_caps_sample_and_notes_total(db_conn):
    result = run_query(db_conn, Intent(camera=["PIE"]))
    assert result.total == 69696  # 288/day * 242 days (2026-01-01..2026-08-30)
    assert len(result.rows) == 50
    assert any("Showing the first 50" in n for n in result.notes)


def test_run_query_B14_flags_partial_dataset_coverage(db_conn):
    result = run_query(db_conn, Intent(date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)))
    assert any("30 Aug 2026" in n for n in result.notes)


def test_run_query_zero_rows_says_so_plainly(db_conn):
    intent = Intent(camera=["PIE"], date_from=date(2026, 8, 30), date_to=date(2026, 8, 30),
                     time_from=time(10, 1), time_to=time(10, 3))
    result = run_query(db_conn, intent)
    assert result.total == 0
    assert result.rows == []
    assert result.notes == ["No frames match those filters."]


def test_format_summary_all_axes():
    result = QueryResult(
        intent=Intent(camera=["CTE"], date_from=date(2026, 8, 24), date_to=date(2026, 8, 30),
                       time_from=time(8, 0), time_to=time(10, 0), days_of_week=[1]),
        total=1247, rows=[], notes=["Showing the first 50 of 1,247."],
    )
    line = format_summary(result)
    assert line.startswith("1,247 frames | CTE | 24-30 Aug 2026 | 08:00-10:00 | Tuesdays only")
    assert "Showing the first 50 of 1,247." in line


def test_format_summary_omits_unset_axes():
    result = QueryResult(intent=Intent(), total=696960, rows=[], notes=[])
    assert format_summary(result) == "696,960 frames"


# --- Validation: refusal, clarification, and bounds checks ---


def test_refuse_passes_through():
    result = resolve_intent(Extraction(action="refuse", message="no cars here"), BOUNDS)
    assert result == Refusal(message="no cars here")


def test_clarify_passes_through():
    result = resolve_intent(Extraction(action="clarify", message="which camera?"), BOUNDS)
    assert result == Clarification(question="which camera?")


def test_unresolvable_camera_phrase_becomes_clarification():
    extraction = Extraction(action="query", camera_phrases=["Jurong Expressway"])
    assert isinstance(resolve_intent(extraction, BOUNDS), Clarification)


def test_A21_validator_catches_a_camera_resolve_camera_would_never_emit(monkeypatch):
    # resolve_camera's own contract never returns anything but one of the ten
    # keys or None; this proves the validator's defense-in-depth check works
    # even if that contract were ever violated.
    monkeypatch.setattr("agent.query.resolve_camera", lambda phrase: "XYZ")
    extraction = Extraction(action="query", camera_phrases=["CTE"])
    assert isinstance(resolve_intent(extraction, BOUNDS), Clarification)


def test_B17_reversed_date_range_swapped_in_code():
    extraction = Extraction(action="query", date_from=date(2026, 8, 18), date_to=date(2026, 8, 15))
    result = resolve_intent(extraction, BOUNDS)
    assert result.date_from == date(2026, 8, 15)
    assert result.date_to == date(2026, 8, 18)


def test_B22_entirely_future_range_is_out_of_range():
    extraction = Extraction(action="query", date_from=date(2027, 1, 1), date_to=date(2027, 1, 1))
    result = resolve_intent(extraction, BOUNDS)
    assert isinstance(result, OutOfRange)
    assert result.available == BOUNDS


def test_B23_entirely_past_range_is_out_of_range():
    extraction = Extraction(action="query", date_from=date(2025, 12, 1), date_to=date(2025, 12, 31))
    assert isinstance(resolve_intent(extraction, BOUNDS), OutOfRange)


def test_B14_partial_overlap_is_not_out_of_range():
    # "the whole of August": date_to runs past the dataset's 30 Aug end, but
    # the range still overlaps real data, so this is a valid Intent, not OutOfRange.
    extraction = Extraction(action="query", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31))
    result = resolve_intent(extraction, BOUNDS)
    assert isinstance(result, Intent)
    assert result.date_to == date(2026, 8, 31)  # not clamped
