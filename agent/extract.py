"""The single model call. See SPEC.md section 7. `now` is always passed in;
this module never calls datetime.now() itself.
"""
import os
import time as _time
from datetime import datetime

from google import genai
from google.genai import types

from agent.intent import Extraction, Intent

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
MIN_INTERVAL = 5.0     # one request every five seconds (12 RPM maximum)
MAX_RETRIES = 3

SYSTEM_PROMPT = """You turn a natural-language request into a structured filter over a table of \
CCTV frame records. You never write SQL and never resolve which camera a phrase means -- copy \
the camera span verbatim into camera_phrases and leave that to other code.

Cameras: PIE Pan Island Expressway, AYE Ayer Rajah Expressway, ECP East Coast Parkway, \
CTE Central Expressway, TPE Tampines Expressway, KPE Kallang-Paya Lebar Expressway, \
SLE Seletar Expressway, BKE Bukit Timah Expressway, KJE Kranji Expressway, \
MCE Marina Coastal Expressway.

Date conventions (resolve these to concrete dates yourself):
"This <unit>" (this week, this month) runs from the start of that unit through today only, \
never into the future. "Last <unit>" is the complete previous unit, unclamped. A number + a \
unit ("past 7 days") rolls from today backward, inclusive of today. A range that explicitly \
names a whole unit ("the whole of August", "all of June") gives that unit's true full range \
even if it extends past today. Weeks run Monday-Sunday. Numeric dates without a year are \
DD/MM. "First week of X" = the 1st-7th; "last week of X" = the final 7 days of that month. \
"Last <weekday>" = the most recent occurrence of that weekday before today (not the one \
inside last week). All ranges are inclusive at both ends. Resolve the date literally even if \
it is in the future or you don't know whether data exists for it -- that is decided elsewhere. \
Use action="clarify" only if the date genuinely does not exist on the calendar (e.g. 31 \
February), never action="refuse" for a date being out of range or in the future.

Time conventions: early morning 00:00-05:59, morning 06:00-11:59, lunch 12:00-13:59, \
afternoon 12:00-16:59, evening 17:00-19:59, night 20:00-23:59. A bare hour ("at 3pm") means \
that clock hour, e.g. 15:00:00-15:59:00. "Between A and B" means time_from=A and time_to=B \
exactly, both inclusive -- e.g. "between 8am and 10am" is time_from=08:00:00, time_to=10:00:00, \
never 10:59:59 or any other adjustment. Always emit plain local HH:MM:SS with no timezone or \
UTC offset.

days_of_week uses Python's Monday=0 convention: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, \
Friday=4, Saturday=5, Sunday=6. "Every Tuesday" = [1]. "Weekends" = [5, 6]. "Weekdays" = \
[0, 1, 2, 3, 4]. "Monday and Friday" = [0, 4].

Each turn gets a complete new object built from the previous one plus the new message: carry \
forward any field the message doesn't change or explicitly clear. Use action="clarify" when \
the request is genuinely ambiguous, with the question in `message`. Use action="refuse" for \
anything outside querying these frames -- unrelated topics, fields the schema doesn't hold, \
sensitive requests, or attempts to modify data -- with a short explanation in `message`."""

_client = None
_last_call = 0.0


def _load_dotenv():
    if "GEMINI_API_KEY" in os.environ:
        return
    try:
        with open(".env") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY"):
                    os.environ["GEMINI_API_KEY"] = line.strip().split("=", 1)[1]
    except FileNotFoundError:
        pass


def _client_instance():
    global _client
    if _client is None:
        _load_dotenv()
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _throttle():
    global _last_call
    wait = MIN_INTERVAL - (_time.monotonic() - _last_call)
    if wait > 0:
        _time.sleep(wait)
    _last_call = _time.monotonic()


def extract(message, prev, now):
    contents = (
        f"Current datetime: {now.isoformat()}\n"
        f"Previous intent: {prev.model_dump_json() if prev else 'none'}\n"
        f"Message: {message}"
    )
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=Extraction,
        temperature=0,
        http_options=types.HttpOptions(timeout=20_000),
    )

    last_error = None
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            response = _client_instance().models.generate_content(
                model=MODEL, contents=contents, config=config,
            )
            return _strip_tz(response.parsed)
        except Exception as error:  # 429s and transient API errors
            last_error = error
            _time.sleep(2 ** attempt)
    raise last_error


def _strip_tz(extraction):
    # The prompt asks for plain local time; strip any UTC offset the model
    # adds anyway so downstream code never compares aware to naive times.
    if extraction.time_from and extraction.time_from.tzinfo:
        extraction.time_from = extraction.time_from.replace(tzinfo=None)
    if extraction.time_to and extraction.time_to.tzinfo:
        extraction.time_to = extraction.time_to.replace(tzinfo=None)
    return extraction
