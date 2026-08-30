"""Conversation state and turn handling. See SPEC.md sections 7-8, 12."""
from datetime import datetime

from agent.extract import extract
from agent.intent import Intent, Outcome, OutOfRange, QueryResult
from agent.query import connect, dataset_bounds, resolve_intent, run_query

_conn = None


def _connection():
    global _conn
    if _conn is None:
        _conn = connect()
    return _conn


def handle_turn(message, prev, now):
    extraction = extract(message, prev, now)
    conn = _connection()
    result = resolve_intent(extraction, dataset_bounds(conn))
    if isinstance(result, Intent):
        return run_query(conn, result)
    return result


def next_state(prev, outcome):
    """SPEC.md section 12: QueryResult and OutOfRange replace state with the
    new intent; Clarification and Refusal leave it unchanged."""
    if isinstance(outcome, (QueryResult, OutOfRange)):
        return outcome.intent
    return prev
