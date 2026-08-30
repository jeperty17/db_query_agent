"""Live Gemini checks for test-matrix.md sections B through E.

The assertion boundary is the validated Intent, never SQL or model prose.
"""
from datetime import date, time

import pytest

from agent.extract import extract
from agent.intent import Clarification, Intent, OutOfRange
from agent.query import resolve_intent
from tests.conftest import NOW_A, NOW_B

BOUNDS = (date(2026, 1, 1), date(2026, 8, 30))


def resolved(message, now):
    return resolve_intent(extract(message, None, now), BOUNDS)


def assert_intent(result, **expected):
    assert isinstance(result, Intent)
    for field, value in expected.items():
        assert getattr(result, field) == value


DATE_CASES = [
    ("B1", "today", NOW_A, date(2026, 8, 30), date(2026, 8, 30)),
    ("B2", "yesterday", NOW_A, date(2026, 8, 29), date(2026, 8, 29)),
    ("B3", "two days ago", NOW_A, date(2026, 8, 28), date(2026, 8, 28)),
    ("B4", "on 15 August", NOW_A, date(2026, 8, 15), date(2026, 8, 15)),
    ("B5", "on 3 March 2026", NOW_A, date(2026, 3, 3), date(2026, 3, 3)),
    ("B6", "on 03/04/2026", NOW_A, date(2026, 4, 3), date(2026, 4, 3)),
    ("B7", "this week", NOW_B, date(2026, 8, 17), date(2026, 8, 19)),
    ("B8", "last week", NOW_B, date(2026, 8, 10), date(2026, 8, 16)),
    ("B9", "the past 7 days", NOW_B, date(2026, 8, 13), date(2026, 8, 19)),
    ("B10", "this week", NOW_A, date(2026, 8, 24), date(2026, 8, 30)),
    ("B11", "last week", NOW_A, date(2026, 8, 17), date(2026, 8, 23)),
    ("B12", "this month", NOW_A, date(2026, 8, 1), date(2026, 8, 30)),
    ("B13", "last month", NOW_A, date(2026, 7, 1), date(2026, 7, 31)),
    ("B14", "the whole of August", NOW_A, date(2026, 8, 1), date(2026, 8, 31)),
    ("B15", "from the 15th to the 18th of last month", NOW_A, date(2026, 7, 15), date(2026, 7, 18)),
    ("B16", "from 5 to 10 August", NOW_A, date(2026, 8, 5), date(2026, 8, 10)),
    ("B17", "from the 18th to the 15th of August", NOW_A, date(2026, 8, 15), date(2026, 8, 18)),
    ("B18", "in June", NOW_A, date(2026, 6, 1), date(2026, 6, 30)),
    ("B19", "first week of August", NOW_A, date(2026, 8, 1), date(2026, 8, 7)),
    ("B20", "last week of July", NOW_A, date(2026, 7, 25), date(2026, 7, 31)),
    ("B24", "last Tuesday", NOW_A, date(2026, 8, 25), date(2026, 8, 25)),
]


@pytest.mark.llm
@pytest.mark.parametrize("case_id,message,now,date_from,date_to", DATE_CASES)
def test_dates(case_id, message, now, date_from, date_to):
    assert_intent(resolved(message, now), camera=[], date_from=date_from, date_to=date_to)


@pytest.mark.llm
def test_B21_invalid_calendar_date_clarifies():
    assert isinstance(resolved("on 31 February", NOW_A), Clarification)


@pytest.mark.llm
@pytest.mark.parametrize("message", ["on 1 January 2027", "in December 2025"])
def test_out_of_range_dates(message):
    assert isinstance(resolved(message, NOW_A), OutOfRange)


TIME_CASES = [
    ("C1", "between 8 AM and 10 AM", time(8), time(10)),
    ("C2", "between 14:00 and 16:00", time(14), time(16)),
    ("C3", "at 3pm", time(15), time(15, 59)),
    ("C4", "in the early morning", time(0), time(5, 59)),
    ("C5", "in the morning", time(6), time(11, 59)),
    ("C6", "around lunch", time(12), time(13, 59)),
    ("C7", "in the afternoon", time(12), time(16, 59)),
    ("C8", "in the evening", time(17), time(19, 59)),
    ("C9", "at night", time(20), time(23, 59)),
    ("C10", "between 10pm and 6am", time(22), time(6)),
    ("C11", "between 10:01 and 10:03", time(10, 1), time(10, 3)),
]


@pytest.mark.llm
@pytest.mark.parametrize("case_id,message,time_from,time_to", TIME_CASES)
def test_times(case_id, message, time_from, time_to):
    assert_intent(resolved(message, NOW_A), camera=[], time_from=time_from, time_to=time_to)


RECURRENCE_CASES = [
    ("D1", "every Tuesday", [1], None, None),
    ("D2", "on weekends", [5, 6], None, None),
    ("D3", "on weekdays", [0, 1, 2, 3, 4], None, None),
    ("D4", "every Tuesday this month", [1], date(2026, 8, 1), date(2026, 8, 30)),
    ("D5", "every Tuesday from 1 to 3 August", [1], date(2026, 8, 1), date(2026, 8, 3)),
    ("D6", "every Monday and Friday last month", [0, 4], date(2026, 7, 1), date(2026, 7, 31)),
]


@pytest.mark.llm
@pytest.mark.parametrize("case_id,message,days,date_from,date_to", RECURRENCE_CASES)
def test_recurrence(case_id, message, days, date_from, date_to):
    assert_intent(resolved(message, NOW_A), camera=[], days_of_week=days, date_from=date_from, date_to=date_to)


COMBINATION_CASES = [
    ("E1", "Show me frames from CTE today", ["CTE"], date(2026, 8, 30), date(2026, 8, 30), None, None, None),
    ("E2", "Show me frames from Tampines Expressway for the whole of August", ["TPE"], date(2026, 8, 1), date(2026, 8, 31), None, None, None),
    ("E3", "Show me frames from MCE on every Tuesday", ["MCE"], None, None, None, None, [1]),
    ("E4", "Show me frames from Kranji Highway from the 15th to 18th of last month", ["KJE"], date(2026, 7, 15), date(2026, 7, 18), None, None, None),
    ("E5", "Show me PIE frames between 8 AM and 10 AM yesterday", ["PIE"], date(2026, 8, 29), date(2026, 8, 29), time(8), time(10), None),
    ("E6", "PIE and CTE between 8am and 10am every Tuesday last month", ["PIE", "CTE"], date(2026, 7, 1), date(2026, 7, 31), time(8), time(10), [1]),
]


@pytest.mark.llm
@pytest.mark.parametrize("case_id,message,camera,date_from,date_to,time_from,time_to,days", COMBINATION_CASES)
def test_combinations(case_id, message, camera, date_from, date_to, time_from, time_to, days):
    assert_intent(
        resolved(message, NOW_A), camera=camera, date_from=date_from, date_to=date_to,
        time_from=time_from, time_to=time_to, days_of_week=days,
    )
