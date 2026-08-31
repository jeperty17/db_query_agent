"""The shared data shapes: the model's raw output, the validated request,
and the possible results the agent can return."""
from dataclasses import dataclass, field
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


@dataclass
class QueryResult:
    intent: Intent
    total: int
    rows: list                       # frame_id, datetime, camera (capped sample)
    notes: list = field(default_factory=list)


@dataclass
class Clarification:
    question: str


@dataclass
class Refusal:
    message: str


@dataclass
class OutOfRange:
    intent: Intent
    requested: tuple
    available: tuple
