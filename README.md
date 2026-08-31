# CCTV Frame Query Agent

An agent that interprets a natural language request, turns it into a database query, and returns the matching CCTV frame records. This is my submission for Cynapse's "Natural Language to Database Query Agent" take-home assignment.

## How it works, in plain terms

1. You type something like `"Show me PIE frames from yesterday morning."`
2. Gemini reads it and produces a structured filter (camera, dates, times,\
   days of week). It never writes SQL and never touches the database.
3. Plain Python checks the filter makes sense: is the camera real, are the\
   dates in order, does the data even cover that range etc.?
4. If it checks out, Python builds a safe, parameterized SQL query and runs\
   it against a **read-only** database connection.
5. You get a one-line summary plus a sample of matching frames.
6. If your message is unclear, off-topic, or asks to change data, the agent\
   asks a clarifying question or refuses. It never guesses or executes anything unsafe.

Only one LLM call fires per turn/request, everything after that call is deterministic, testable Python with no API involved.

## Setup

```sh
python3 -m pip install -r requirements.txt
printf 'GEMINI_API_KEY=your-key\n' > .env
python3 setup_db.py
python3 cli.py
```

`setup_db.py` generates `frames.db`: one frame per camera every 5 minutes,\
from 2026-01-01 through today. Takes a few seconds. Safe to rerun since it only adds days that are missing.

## Running tests

```sh
python3 -m pytest -m 'not llm'   # fast, no API calls
python3 -m pytest -m llm         # slower, hits the real Gemini API
```

## What you can ask it

**Cameras**: full name, acronym, a common alternate name, or a typo all work:

```plaintext
PIE
Central Expressway
Kranji Highway
Tampines Expresway      (typo)
marina                  (partial name)
```

**Dates**: exact, relative, or a named range:

```plaintext
today / yesterday / last week / this month
the whole of August
15th to 18th of last month
31/08                    (day/month order)
last Tuesday
```

All date and time ranges are inclusive at both ends: "between 8am and 10am" includes the 10:00 frame.

| Expression | Meaning |
| --- | --- |
| `last`/`this` + a calendar unit | that calendar unit itself, not a rolling window |
| a number + a unit ("past 7 days") | rolling from today, inclusive of today |
| week boundaries | Monday to Sunday |
| numeric dates | DD/MM |
| "first week of X" | the 1st to the 7th |
| "last week of X" | the final 7 days of the month |
| "last `<weekday>`" | the most recent occurrence before today |

"Last week" and "the past 7 days" are different on purpose: last week is the
previous Monday-to-Sunday block, the past 7 days rolls from today backward.
Same distinction applies to "last Tuesday": it's the most recent Tuesday,
not the Tuesday inside last week.

**Times**: named windows, a bare hour, a range, or overnight:

```plaintext
morning / afternoon / evening
at 3pm
between 8am and 10am
between 10pm and 6am     (crosses midnight, handled correctly)
```

| Term | Range |
| --- | --- |
| early morning | 00:00 to 05:59 |
| morning | 06:00 to 11:59 |
| lunch | 12:00 to 13:59 |
| afternoon | 12:00 to 16:59 |
| evening | 17:00 to 19:59 |
| night | 20:00 to 23:59 |

A bare hour like "at 3pm" means that whole clock hour: 15:00 to 15:59.

**Days of week**: recurring filters:

```plaintext
every Tuesday
weekends / weekdays
```

**Combine anything:**

```plaintext
Show me PIE frames between 8am and 10am yesterday.
```

**Follow-ups**: it remembers what you asked last turn:

```plaintext
You:  Show me frames from CTE.
You:  How about only this week?     → still CTE, now with a date filter
You:  Only mornings.                → still CTE, still this week, now mornings only
You:  Show me MCE frames.           → a full new request, starts over
```

**It will refuse:**

- Anything unrelated to CCTV frames
- Requests for things the data doesn't hold: images, license plates,\
  people, vehicle counts
- Any request to add, change, or delete data
- Attempts to see its own instructions
- SQL injection attempts (treated as plain text, never executed)

**It will ask you to clarify** instead of guessing:

- Vague requests ("recent frames", "some frames")
- Ambiguous references ("the other one", "just the first one")
- A number with no unit ("frames from 8" - the 8th, or 8 o'clock?)

## Why it's built this way

_This section covers agent architecture, tool/model choices, and the\
reasoning behind them._

### One LLM call, not a multi-step agent

The given task is straightforward: to turn one sentence into a filter with a handful of\
fields. This doesn't need planning, tool loops, or multi-step reasoning to extract the necessary information, so a single call is simpler, cheaper, faster, and far easier to test than a multi-step agent, and it avoids over-engineering or any unnecessary complexity. Everything after the extraction, such as validation, SQL building, query execution, is plain deterministic Python, so it's reproducible and testable without hitting an API at all in order to manage API costs.

### Model choice

The default model I use is `gemini-3.1-flash-lite`, because it gives the most generous number of requests on the free Gemini API tier, so it's what the whole test\
suite runs against. Alternative is `gemini-3.5-flash-lite`.

I added client-side rate limiting (a 5-second minimum gap between calls, so at most 12 requests a minute) purely to avoid tripping the free tier's per-minute and per-day quotas. `GEMINI_MODEL` overrides the default if you have a paid key and want to try a bigger model.

This task doesn't need a large model since it is a narrow, structured extraction\
into a fixed schema. A small, fast, free model is most ideal when considering the speed/complexity trade-off, as well as from an overall cost standpoint.

### Structured LLM output

The Gemini SDK's schema-constrained output (`response_schema` backed by a\
Pydantic model) forces the model's reply into a fixed shape, in the form of an Intent object that I defined. The model therefore does not write any SQL queries on its own, and its only function is to understand the user's natural language request and produce the Intent object, which the rest of the code will subsequently process and write the SQL queries etc.

### Camera matching: fuzzy scoring, calibrated against real cases

The model never resolves a camera name itself, it instead copies whatever\
span of text the user used, verbatim. A separate, deterministic function\
(`agent/cameras.py`) then does the matching:

1. Exact acronym ("PIE") matches immediately.
2. Otherwise, normalize the text, strip the trailing expressway word ("expressway",\
   "highway", ...), and fuzzy-match it against the 10 known camera names\
   using `rapidfuzz`.
3. A match only counts if it clears a **score floor** and beats the\
   runner-up by a **margin**, so a fuzzy match has to be both good and\
   unambiguous.

The floor (70) and margin (10) are derived from `agent/calibrate.py` which scores every accepted and rejected phrase in the test matrix against the real\
camera names and prints where genuine matches and decoys land to infer a reasonable floor and margin between 1st and 2nd choice for highest similarity.

The road-word stripping step itself is also fuzzy-matched (not just an exact\
set lookup), so a misspelled road word ("expresswy") still gets recognized\
and stripped correctly, using the same `rapidfuzz` dependency already in\
the project.

If a phrase can't be resolved to a real camera confidently, the agent asks\
for clarification instead of guessing or passing a hallucinated value\
through to the database.

### Follow-ups: model carries over the context

The previous turn's validated intent (not raw chat history) is passed back\
into every model call as structured data. The prompt explicitly teaches the\
model to tell an elliptical follow-up ("only this week") which edits the\
previous filter and keeps everything else, apart from a full new request\
("show me MCE frames"), which starts over.

### Guardrails

1. **Prompt-level:** explicit refusal rules for off-topic requests, fields\
   the schema doesn't hold (images, plates, people, vehicle counts), data\
   mutation requests, and prompt-disclosure attempts, with actual injection\
   examples worked into the prompt itself (SQL fragments, "ignore previous\
   instructions"), so the model has seen the exact shape of the attack, and not\
   just an abstract instruction to resist it.
2. **Schema-level:** the model's output can only ever contain fields from a\
   fixed schema. There's no field for SQL or a mutation verb, so there's\
   nothing for it to misuse even if it wanted to.
3. **Code-level:** every value that reaches SQL is a bound parameter, never\
   string-interpolated. The database connection itself is opened read-only\
   at the SQLite driver level (`mode=ro`), so even a bug elsewhere in the\
   code physically cannot write to the database.
4. **Resolver-level:** if the model's camera phrase doesn't match a real\
   camera closely enough, the agent clarifies rather than letting a\
   hallucinated value reach the query.

### Testing: fast deterministic tests, separate from slow live-model tests

Tests are split by `pytest` marker. Anything that doesn't need the API, such as\
camera resolution, SQL building, date formatting, runs in a fraction of a\
second with no API cost. Anything that needs to check actual model\
behavior (date/time reasoning, guardrails, follow-ups) is marked `llm` and\
hits the real Gemini API.

## Repo layout

```plaintext
cli.py                 The command-line chat loop you run to talk to the agent.
setup_db.py            Creates the sample CCTV frame database that the agent queries.

agent/
  intent.py            The shared data shapes: the model's raw output, the
                        validated request, and the possible results the
                        agent can return.
  extract.py           Sends the user's message to Gemini and gets back a
                        structured request.
  cameras.py           Matches whatever camera name the user typed to one
                        of the real cameras.
  calibrate.py         Dev tool: checks that the camera-matching settings
                        are tuned correctly.
  camera_cases.py      Example camera names, typos, and nicknames, with
                        the camera each should match.
  query.py             Turns a validated request into a database query,
                        runs it, and formats the results.
  session.py           Keeps track of the conversation so follow-up
                        questions make sense.

tests/
  conftest.py          Shared setup used by every test: a fixed date/time
                        and a test-only database.
  test_cameras.py      Tests that camera names, nicknames, and typos all
                        resolve to the right camera.
  test_query.py        Tests that requests turn into correct, safe
                        database queries.
  test_extraction.py   Checks that the agent correctly understands dates,
                        times, and cameras from natural language.
  test_followups.py    Checks that follow-up messages correctly build on
                        the previous request.
  test_guardrails.py   Checks that the agent refuses unsafe, off-topic,
                        or malicious requests.
  test_responses.py    Checks that results and clarification questions
                        are worded clearly.

docs/                  The assignment PDF, plus internal working notes
                        (spec, test matrix, build progress) kept for
                        anyone who wants the full history behind this
                        README.
```
