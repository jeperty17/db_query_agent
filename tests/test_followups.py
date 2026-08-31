"""Live Gemini checks for test-matrix.md section F."""
from datetime import date, time

import pytest

from agent.intent import Clarification, Refusal
from agent.session import next_state
from tests.conftest import assert_intent, resolved


def turn(message, prev):
    outcome = resolved(message, prev=prev)
    return outcome, next_state(prev, outcome)


@pytest.mark.llm
@pytest.mark.parametrize("turns, expected", [
    (("show me frames from CTE", "how about only this week"), ({"camera": ["CTE"]}, {"camera": ["CTE"], "date_from": date(2026, 8, 24), "date_to": date(2026, 8, 30)})),
    (("show me CTE frames this week", "how about MCE"), ({"camera": ["CTE"]}, {"camera": ["MCE"], "date_from": date(2026, 8, 24), "date_to": date(2026, 8, 30)})),
    (("show me CTE frames this week", "actually show me everything from yesterday"), ({"camera": ["CTE"]}, {"camera": [], "date_from": date(2026, 8, 29), "date_to": date(2026, 8, 29)})),
    (("show me CTE frames this week", "what about last month"), ({"camera": ["CTE"]}, {"camera": ["CTE"], "date_from": date(2026, 7, 1), "date_to": date(2026, 7, 31)})),
    (("show me CTE frames yesterday", "only in the morning"), ({"camera": ["CTE"]}, {"camera": ["CTE"], "date_from": date(2026, 8, 29), "date_to": date(2026, 8, 29), "time_from": time(6), "time_to": time(11, 59)})),
    (("show me CTE frames this week", "show me MCE frames"), ({"camera": ["CTE"]}, {"camera": ["MCE"], "date_from": None, "date_to": None})),
    (("show me frames from last week", "only the Kranji one"), ({"camera": []}, {"camera": ["KJE"], "date_from": date(2026, 8, 17), "date_to": date(2026, 8, 23)})),
    (("show me MCE frames last month", "only on Tuesdays"), ({"camera": ["MCE"]}, {"camera": ["MCE"], "date_from": date(2026, 7, 1), "date_to": date(2026, 7, 31), "days_of_week": [1]})),
])
def test_followups(turns, expected):
    prev = None
    for message, fields in zip(turns, expected):
        outcome, prev = turn(message, prev)
        assert_intent(outcome, **fields)


@pytest.mark.llm
def test_F7_refusal_keeps_prior_state():
    first, prev = turn("show me CTE frames", None)
    assert_intent(first, camera=["CTE"])
    refusal, unchanged = turn("what's the weather", prev)
    assert isinstance(refusal, Refusal) and unchanged == prev
    final, _ = turn("how about yesterday", unchanged)
    assert_intent(final, camera=["CTE"], date_from=date(2026, 8, 29), date_to=date(2026, 8, 29))


@pytest.mark.llm
def test_F8_ambiguity_keeps_prior_state():
    first, prev = turn("show me PIE and CTE frames", None)
    assert_intent(first, camera=["PIE", "CTE"])
    outcome, unchanged = turn("just the other one", prev)
    assert isinstance(outcome, Clarification) and unchanged == prev
