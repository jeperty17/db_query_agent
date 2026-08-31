"""Response-shape checks for test-matrix.md sections H and I."""
from datetime import date

import pytest

from agent.intent import Clarification, Intent, OutOfRange
from agent.query import run_query
from tests.conftest import resolved


def test_H1_full_range_is_capped(db_conn):
    result = run_query(db_conn, Intent(camera=["PIE"]))
    assert result.total == 69696 and len(result.rows) == 50
    assert "Showing the first 50" in result.notes[0]


def test_H2_partial_data_coverage_is_not_clamped(db_conn):
    result = run_query(db_conn, Intent(date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)))
    assert result.total == 86400
    assert any("30 Aug 2026" in note for note in result.notes)


@pytest.mark.llm
def test_H3_out_of_range_is_not_an_empty_result():
    result = resolved("show me PIE frames on 1 January 2027")
    assert isinstance(result, OutOfRange)


def test_H4_valid_zero_rows_explains_it(db_conn):
    result = run_query(db_conn, Intent(camera=["MCE"], days_of_week=[1], date_from=date(2026, 8, 1), date_to=date(2026, 8, 3)))
    assert result.total == 0 and result.notes == ["No frames match those filters."]


@pytest.mark.llm
@pytest.mark.parametrize("message", [
    "show me frames from the expressway", "show me recent frames", "show me Jurong Expressway frames",
    "show me some frames", "show me CTE frames from 8",
])
def test_ambiguities_clarify(message):
    result = resolved(message)
    assert isinstance(result, Clarification)
