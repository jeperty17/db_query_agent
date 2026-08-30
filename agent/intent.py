"""The intent object, the model's raw extraction, and the four turn outcomes.

See SPEC.md sections 5, 7, and 12.
"""
from datetime import date, time

from pydantic import create_model

NONE_TYPE = type(None)


Intent = create_model(
    "Intent",
    camera=(list, []),              # resolved acronyms; [] means all cameras
    date_from=(date | NONE_TYPE, None),
    date_to=(date | NONE_TYPE, None),
    time_from=(time | NONE_TYPE, None),
    time_to=(time | NONE_TYPE, None),
    days_of_week=(list | NONE_TYPE, None),  # 0=Mon .. 6=Sun
)


Extraction = create_model(
    "Extraction",
    action=(str, ...),
    camera_phrases=(list, []),      # verbatim spans from the message
    date_from=(date | NONE_TYPE, None),
    date_to=(date | NONE_TYPE, None),
    time_from=(time | NONE_TYPE, None),
    time_to=(time | NONE_TYPE, None),
    days_of_week=(list | NONE_TYPE, None),
    message=(str | NONE_TYPE, None),  # text for clarify and refuse
)


class _Outcome:
    def __eq__(self, other):
        return type(self) is type(other) and self.__dict__ == other.__dict__


class QueryResult(_Outcome):
    def __init__(self, intent, total, rows, notes=None):
        self.intent = intent
        self.total = total
        self.rows = rows             # frame_id, datetime, camera (capped sample)
        self.notes = [] if notes is None else notes


class Clarification(_Outcome):
    def __init__(self, question):
        self.question = question


class Refusal(_Outcome):
    def __init__(self, message):
        self.message = message


class OutOfRange(_Outcome):
    def __init__(self, intent, requested, available):
        self.intent = intent
        self.requested = requested
        self.available = available


Outcome = (QueryResult, Clarification, Refusal, OutOfRange)
