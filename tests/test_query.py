"""Query builder correctness. Hand-built Intent objects, real database. No API calls.

See SPEC.md section 11 and test-matrix.md section C / D7.
"""
from datetime import date, time

from agent.intent import Intent, QueryResult
from agent.query import build_query, format_summary, run_query


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
