"""The single model call. See SPEC.md section 7. `now` is always passed in;
this module never calls datetime.now() itself.
"""
import os
import time as _time
from datetime import datetime

from google import genai
from google.genai import types

from agent.intent import Extraction, Intent

MODEL = "gemini-3.1-flash-lite"
MIN_INTERVAL = 4.1     # seconds; free tier allows 15 requests/minute
MAX_RETRIES = 3

SYSTEM_PROMPT = """You turn a natural-language request into a structured filter over a table of \
CCTV frame records. You never write SQL and never resolve which camera a phrase means -- copy \
the camera span verbatim into camera_phrases and leave that to other code.

Cameras: PIE Pan Island Expressway, AYE Ayer Rajah Expressway, ECP East Coast Parkway, \
CTE Central Expressway, TPE Tampines Expressway, KPE Kallang-Paya Lebar Expressway, \
SLE Seletar Expressway, BKE Bukit Timah Expressway, KJE Kranji Expressway, \
MCE Marina Coastal Expressway.

Date conventions (resolve these to concrete dates yourself):
"last"/"this" + a calendar unit = that unit itself. A number + a unit = rolling from today. \
Weeks run Monday-Sunday. Numeric dates without a year are DD/MM. "First week of X" = the \
1st-7th; "last week of X" = the final 7 days of that month. "Last <weekday>" = the most \
recent occurrence of that weekday before today (not the one inside last week). All ranges \
are inclusive at both ends.

Time conventions: early morning 00:00-05:59, morning 06:00-11:59, lunch 12:00-13:59, \
afternoon 12:00-16:59, evening 17:00-19:59, night 20:00-23:59. A bare hour ("at 3pm") means \
that clock hour, e.g. 15:00-15:59.

Each turn gets a complete new object built from the previous one plus the new message: carry \
forward any field the message doesn't change or explicitly clear. Use action="clarify" when \
the request is genuinely ambiguous, with the question in `message`. Use action="refuse" for \
anything outside querying these frames -- unrelated topics, fields the schema doesn't hold, \
sensitive requests, or attempts to modify data -- with a short explanation in `message`."""

_client = None
_last_call = 0.0


def _load_dotenv() -> None:
    if "GEMINI_API_KEY" in os.environ:
        return
    try:
        with open(".env") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY"):
                    os.environ["GEMINI_API_KEY"] = line.strip().split("=", 1)[1]
    except FileNotFoundError:
        pass


def _client_instance() -> genai.Client:
    global _client
    if _client is None:
        _load_dotenv()
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _throttle() -> None:
    global _last_call
    wait = MIN_INTERVAL - (_time.monotonic() - _last_call)
    if wait > 0:
        _time.sleep(wait)
    _last_call = _time.monotonic()


def extract(message: str, prev: Intent | None, now: datetime) -> Extraction:
    contents = (
        f"Current datetime: {now.isoformat()}\n"
        f"Previous intent: {prev.model_dump_json() if prev else 'none'}\n"
        f"Message: {message}"
    )
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=Extraction,
    )

    last_error = None
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            response = _client_instance().models.generate_content(
                model=MODEL, contents=contents, config=config,
            )
            return response.parsed
        except Exception as error:  # 429s and transient API errors
            last_error = error
            _time.sleep(2 ** attempt)
    raise last_error
