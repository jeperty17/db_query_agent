"""The intent object, the model's raw extraction, and the four turn outcomes.

See SPEC.md sections 5, 7, and 12.
"""
from dataclasses import dataclass, field
from datetime import date, time
from typing import Literal, Union

from pydantic import BaseModel


class Intent(BaseModel):
    camera: list[str] = []          # resolved acronyms; [] means all cameras
    date_from: date | None = None
    date_to: date | None = None
    time_from: time | None = None
    time_to: time | None = None
    days_of_week: list[int] | None = None  # 0=Mon .. 6=Sun


class Extraction(BaseModel):
    action: Literal["query", "clarify", "refuse"]
    camera_phrases: list[str] = []  # verbatim spans from the message
    date_from: date | None = None
    date_to: date | None = None
    time_from: time | None = None
    time_to: time | None = None
    days_of_week: list[int] | None = None
    message: str | None = None      # text for clarify and refuse


@dataclass
class QueryResult:
    intent: Intent
    total: int
    rows: list[tuple[int, str, str]]  # frame_id, datetime, camera (capped sample)
    notes: list[str] = field(default_factory=list)


@dataclass
class Clarification:
    question: str


@dataclass
class Refusal:
    message: str


@dataclass
class OutOfRange:
    intent: Intent
    requested: tuple[date | None, date | None]
    available: tuple[date, date]


Outcome = Union[QueryResult, Clarification, Refusal, OutOfRange]
