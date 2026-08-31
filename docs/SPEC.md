# Spec: Natural Language to Database Query Agent

Build an agent that turns natural language requests into database queries over a table of CCTV frame records and returns the matching frames.

The test matrix in `test-matrix.md` is the source of truth for correct behaviour. Read it before writing code.

Section 18 gives the build order. Follow it.

---

## 1. Guiding principle

The language model handles language. Code handles data.

The model's only job is to read a message and emit a structured object. It never writes SQL, never touches the database, and never decides which of the ten cameras a phrase refers to. Everything after the model call is deterministic Python.

This is what makes the system testable, and it is also the main guardrail. A user cannot make the system delete records because the object the model produces has no way to express deletion.

---

## 2. Stack

| Piece          | Choice                                     | Why                                                                                                                                                                                                                                                    |
| -------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Language       | Python 3.11+                               | `date`, `time` and `datetime` in the standard library cover every date operation needed here.                                                                                                                                                          |
| Database       | SQLite, stdlib `sqlite3`                   | One table, around 700k rows, single user. A server database would add setup steps and no capability. SQLite also supports opening a connection read-only, which is used as a guardrail.                                                                |
| Schemas        | `pydantic`                                 | The intent object needs validation and the Gemini SDK can enforce a pydantic schema on the model's output directly, so malformed JSON never reaches the code.                                                                                          |
| Fuzzy matching | `rapidfuzz`                                | Used in one function, for camera stems. Fast and has the scorers needed.                                                                                                                                                                               |
| Model          | Gemini 3.1 Flash Lite, then 3.5 Flash Lite | The task is constrained extraction against a ten-value enum, not hard reasoning, so a small fast model is the right size. Both sit on the free tier, so cost is zero. Start with 3.1 Flash Lite and move up only if the suite shows it dropping cases. |
| Tests          | `pytest`                                   | Parametrised cases map directly onto the test matrix rows.                                                                                                                                                                                             |

Keep the dependency list to these four. Nothing else.

---

## 3. Project layout

```
README.md
requirements.txt
setup_db.py            # generates the dataset
cli.py                 # interactive loop
benchmark.py           # runs the suite against several models
agent/
    intent.py          # Intent, Extraction, and outcome types
    cameras.py         # camera phrase -> enum
    extract.py         # the single model call
    query.py           # query builder, execution, response shaping
    session.py         # conversation state and turn handling
tests/
    conftest.py        # frozen clocks, db fixture
    test_cameras.py    # section A, no API calls
    test_query.py      # query builder, no API calls
    test_extraction.py # sections B to E, hits the model
    test_followups.py  # section F, hits the model
    test_guardrails.py # section G, hits the model
    test_responses.py  # sections H and I
```

---

## 4. Dataset

### Schema

```sql
CREATE TABLE frames (
    frame_id     INTEGER PRIMARY KEY,
    datetime     TEXT    NOT NULL,   -- ISO 8601, e.g. 2026-08-30T14:30:00
    camera       TEXT    NOT NULL,   -- one of the ten acronyms
    frame_date   TEXT    NOT NULL,   -- YYYY-MM-DD
    frame_time   TEXT    NOT NULL,   -- HH:MM
    day_of_week  INTEGER NOT NULL    -- 0=Monday .. 6=Sunday
);

CREATE INDEX idx_frames_lookup ON frames(camera, frame_date, frame_time);
CREATE INDEX idx_frames_dow    ON frames(day_of_week);
```

`datetime` is the record as specified in the brief. The other three columns are derived from it at generation time.

Why derive them: queries filter on date range, time of day, and day of week as three independent axes. Storing them as separate columns makes each one a plain indexed comparison.

Deriving `day_of_week` in Python also removes a real bug. Python's `date.weekday()` is 0=Monday. SQLite's `strftime('%w')` is 0=Sunday. Computing it once in Python at generation time means there is only ever one convention in the system.

### Cameras

```python
CAMERAS = {
    "PIE": "Pan Island Expressway",
    "AYE": "Ayer Rajah Expressway",
    "ECP": "East Coast Parkway",
    "CTE": "Central Expressway",
    "TPE": "Tampines Expressway",
    "KPE": "Kallang-Paya Lebar Expressway",
    "SLE": "Seletar Expressway",
    "BKE": "Bukit Timah Expressway",
    "KJE": "Kranji Expressway",
    "MCE": "Marina Coastal Expressway",
}
```

### Generation

`setup_db.py` writes one frame per camera every 5 minutes, from `2026-01-01T00:00:00` through the end of the current date. All times are Singapore local. No timezone conversion anywhere in the system.

That is 288 frames per camera per day, so roughly 700k rows for a run in late August.

Requirements:

- Insert with `executemany` inside a single transaction. A row-at-a-time loop takes minutes; this takes seconds.
- Idempotent. If the database exists, read `MAX(frame_date)` and append only the missing days. If it does not exist, generate everything.
- Print the row count and the date span when finished.

Why generate through the real current date rather than a fixed one: users will type "today" and expect frames back. The tests do not depend on this, because they pass their own clock (section 8).

---

## 5. The intent object

```python
class Intent(BaseModel):
    camera:       list[str] = []          # resolved acronyms; [] means all cameras
    date_from:    date | None = None
    date_to:      date | None = None
    time_from:    time | None = None
    time_to:      time | None = None
    days_of_week: list[int] | None = None # 0=Mon .. 6=Sun
```

Every field is optional. An absent field means no filter on that axis.

Two things about this shape are load-bearing.

**Date and time are separate axes.** A single start and end datetime cannot express "between 8am and 10am every day last week", because that is not one continuous span. Keeping them apart makes date range, time of day, and day of week compose freely.

**`camera` is a list.** It costs nothing now and allows "PIE and CTE" without a schema change. Empty list means every camera, which is also what a query with no camera mentioned resolves to.

`days_of_week` is a day filter, not a general recurrence rule. The name is deliberate.

---

## 6. Camera resolution

Lives in `agent/cameras.py`. Pure function, no API call.

```python
def resolve_camera(phrase: str) -> str | None
```

Steps in order:

1. Normalise. Lowercase, strip punctuation, collapse whitespace.
2. If the phrase is exactly one of the ten acronyms, return it.
3. Strip a trailing road-type word: `expressway`, `highway`, `parkway`, `expwy`, `expy`, `road`.
4. Fuzzy match the remaining stem against the ten stems (`pan island`, `ayer rajah`, `east coast`, `central`, `tampines`, `kallang-paya lebar`, `seletar`, `bukit timah`, `kranji`, `marina coastal`).
5. Accept the best match only if it clears the score floor **and** beats the runner-up by the margin. Otherwise return `None`, which the caller turns into a clarification.

Why strip the road-type word: all ten are expressways, so that word carries no information and creates collisions. "Tampines Parkway" scores against "East Coast Parkway" on the shared word under token-based scorers. Removing it leaves ten well-separated stems and makes bare "Tampines" and "East Coast" work by exact match.

Why acronyms are matched exactly: a three-letter string is either one of the ten cameras or it is not. If it is, that is the camera the user named. If it is not, ask. TPE, KPE and KJE sit one character apart, so any correction applied to a valid acronym would be invented rather than inferred.

Calibrate the floor and margin with the script described in section J of the test matrix, then hard-code the numbers and record them in the README.

---

## 7. The model call

Lives in `agent/extract.py`. One call per turn. No chain, no router, no multi-agent step.

### Output schema

```python
class Extraction(BaseModel):
    action:         Literal["query", "clarify", "refuse"]
    camera_phrases: list[str] = []        # verbatim spans from the message
    date_from:      date | None = None
    date_to:        date | None = None
    time_from:      time | None = None
    time_to:        time | None = None
    days_of_week:   list[int] | None = None
    message:        str | None = None     # text for clarify and refuse
```

Use the SDK's schema enforcement so the response is guaranteed to parse.

### Division of labour

The model resolves dates and times to concrete values. It is given the current datetime and the convention table in the prompt.

The model does not resolve cameras. It copies the camera span out of the message verbatim, and `resolve_camera` maps it.

Why the split: there are ten cameras and unlimited ways to phrase a date. A closed answer set is worth resolving in code, because the code is small and a wrong camera fails silently. Date phrasing is open-ended, and writing a parser for it would be more code than the whole rest of the system.

A useful side effect: every case in section A of the test matrix is a pure function test with no API call, so camera behaviour is verified in milliseconds.

### Prompt contents

Keep it short. Long system prompts are penalised.

- One line on role and scope.
- The ten cameras with full names and acronyms.
- The date convention table from section 9.
- The time bucket table from section 9.
- The current datetime, injected per call.
- The previous intent object, serialised, or "none".
- Instruction to carry unchanged fields forward into the new object.
- Instruction to use `refuse` for anything outside querying these frames, and `clarify` when the request is genuinely ambiguous.

### Turn handling

Each turn sends the previous intent object plus the new message and gets back a complete new object. There is no merge step.

Why complete objects: a follow-up like "actually show me everything from yesterday" needs to clear the camera filter. An object that only carries changes cannot distinguish "leave this field alone" from "remove this field" without extra machinery. A complete object handles it by simply not containing the field.

The cost is that the model has to remember to carry forward fields that should persist. Section F of the test matrix asserts the full object after every turn, which catches a dropped field immediately.

Note what is carried between turns: six fields, not a growing transcript. Context stays flat however long the conversation runs.

---

## 8. Clock injection

Every function that resolves a relative expression takes `now` as an argument. Nothing calls `datetime.now()` internally except the entry point in `cli.py`.

```python
def handle_turn(message: str, prev: Intent | None, now: datetime) -> Outcome
```

Production passes the real clock. Tests pass a frozen one. Same function.

Test clocks:

```python
NOW_A = datetime(2026, 8, 30, 14, 30)   # Sunday
NOW_B = datetime(2026, 8, 19,  9,  0)   # Wednesday
```

`NOW_B` exists because on a Sunday "this week" and "past 7 days" resolve to the same range, which would hide a bug in either.

---

## 9. Conventions

These go in the prompt and in the README. The expected values in the test matrix depend on them.

**All date and time ranges are inclusive at both ends.** "Between 8am and 10am" returns the 10:00 frame. The query builder uses `>=` and `<=` throughout, so this falls out naturally, but it has to be stated because a user cannot guess it.

### Dates

| Expression                            | Meaning                                 |
| ------------------------------------- | --------------------------------------- |
| `last` or `this` plus a calendar unit | the calendar unit itself                |
| a number plus a unit                  | rolling from today                      |
| week boundaries                       | Monday to Sunday                        |
| numeric dates                         | DD/MM                                   |
| "first week of X"                     | the 1st to the 7th                      |
| "last week of X"                      | the final 7 days of the month           |
| "last `<weekday>`"                    | the most recent occurrence before today |

So "last week" is the previous Monday to Sunday, and "the past 7 days" is today minus 6 through today. They are different and both are supported.

"Last Tuesday" is the most recent Tuesday, not the Tuesday inside last week. On Sunday 30 August those are 25 August and 18 August respectively, so the choice is visible and has to be documented.

### Times

| Term          | Range          |
| ------------- | -------------- |
| early morning | 00:00 to 05:59 |
| morning       | 06:00 to 11:59 |
| lunch         | 12:00 to 13:59 |
| afternoon     | 12:00 to 16:59 |
| evening       | 17:00 to 19:59 |
| night         | 20:00 to 23:59 |

A bare hour like "at 3pm" means that clock hour, 15:00 to 15:59.

No bucket crosses midnight, so the common cases produce a simple range. Endpoints stop at :59 because the bounds are inclusive.

---

## 10. Validation

Runs after extraction, before the query. All in code.

1. **Resolve cameras.** Map each phrase through `resolve_camera`. Any phrase returning `None` makes the whole turn a clarification.
2. **Reject unknown cameras.** If a resolved value is somehow not one of the ten, return a clarification. A hallucinated camera reaching the query would return zero rows, which reads to the user as "no frames exist" rather than "I misheard you".
3. **Swap reversed date ranges.** If `date_from > date_to`, swap them. A backwards date range is meaningless, so it is a user error with an obvious fix.
4. **Leave reversed time ranges alone.** If `time_from > time_to`, that is an overnight range and the query builder handles it. Dates are linear, times are cyclic.
5. **Check data bounds.** If the resolved date range falls entirely outside the dataset span, return `OutOfRange`.

---

## 11. Query builder

Lives in `agent/query.py`. One builder. Each present field contributes one clause.

```python
def build_query(intent: Intent) -> tuple[str, list]:
    clauses, params = [], []

    if intent.camera:
        placeholders = ",".join("?" * len(intent.camera))
        clauses.append(f"camera IN ({placeholders})")
        params.extend(intent.camera)

    if intent.date_from:
        clauses.append("frame_date >= ?")
        params.append(intent.date_from.isoformat())

    if intent.date_to:
        clauses.append("frame_date <= ?")
        params.append(intent.date_to.isoformat())

    if intent.time_from and intent.time_to:
        a = intent.time_from.strftime("%H:%M")
        b = intent.time_to.strftime("%H:%M")
        if intent.time_from <= intent.time_to:
            clauses.append("frame_time >= ? AND frame_time <= ?")
        else:
            clauses.append("(frame_time >= ? OR frame_time <= ?)")   # overnight
        params.extend([a, b])

    if intent.days_of_week:
        placeholders = ",".join("?" * len(intent.days_of_week))
        clauses.append(f"day_of_week IN ({placeholders})")
        params.extend(intent.days_of_week)

    sql = "SELECT frame_id, datetime, camera FROM frames"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return sql + " ORDER BY datetime", params
```

**Every value is a bound parameter.** The only thing built with an f-string is the number of `?` placeholders, which is derived from a list length and never from user text. No user-supplied string is ever concatenated into SQL.

The overnight branch evaluates inside each day of the date range. It does not extend `date_to`. Extending the date would couple the two axes back together and break every other case.

### Execution

Open read-only:

```python
sqlite3.connect("file:frames.db?mode=ro", uri=True)
```

Any write reaching the driver raises. This is the second layer under the intent object having no verb.

### Result shaping

1. `SELECT COUNT(*)` with the same WHERE clause.
2. Return the first 50 rows ordered by datetime, or all of them if there are fewer.
3. Print a summary line above the rows that reads the resolved intent back in plain English.

The summary line is the important part:

```
1,247 frames | CTE | 24-30 Aug 2026 | 08:00-10:00 | Tuesdays only
Showing the first 50.
```

Include only the axes that are actually filtered. Omit an unset field rather than printing "any".

Why the summary matters more than the rows: a frame carries a frame ID, a timestamp and a camera name, so reading fifty of them tells the user very little. The summary tells them whether the system understood the request, which is the thing they need to check.

The query itself is never narrowed. If a user asks for every Tuesday, the count covers every Tuesday. Only the returned rows are capped, and the response says so.

---

## 12. Outcomes

Four types. Each says what happens to conversation state.

| Type            | Contents                                           | State                        |
| --------------- | -------------------------------------------------- | ---------------------------- |
| `QueryResult`   | total count, date span covered, sample rows, notes | replaced with the new intent |
| `Clarification` | a question                                         | unchanged                    |
| `Refusal`       | what the system does support                       | unchanged                    |
| `OutOfRange`    | the requested span and the available span          | replaced with the new intent |

State handling is the important part. If a refusal wipes state, every follow-up after one bad input dies. Test F7 covers this.

`OutOfRange` replaces state because the intent was understood correctly; only the data was missing.

### Notes on `QueryResult`

Add a note when either applies:

- the sample was capped, giving the total
- the requested range extends past the dataset, giving the actual coverage

A query that is valid and genuinely returns zero rows says so plainly, and is distinct from `OutOfRange`. Two ways this happens: a day filter with no matching day in the range, and a time window narrower than the 5-minute sampling interval.

---

## 13. Guardrails

Four layers, in order of strength.

1. **The intent object has no verb.** It holds filters only. "Delete all frames from PIE" has no representation in it. This is structural, not an instruction the model can be talked out of.
2. **Read-only connection.** Writes fail at the driver.
3. **Bound parameters.** No user text ever becomes part of a SQL string.
4. **Prompt scope statement.** A short instruction to use `refuse` for out-of-scope requests, which produces a useful message rather than a confusing empty result.

Distinguish three kinds of refusal in the message text.

**Unrelated.** An off-topic question gets "this system queries CCTV frame records".

**Unsupported field.** A request for data the schema does not hold, such as how many cars are in a frame, gets a message naming the three fields that do exist. It is a real query about genuinely absent data, so "out of scope" would read as broken.

**Sensitive.** Requests to identify a person, trace a vehicle, or read a licence plate get the same shape as an unsupported field, because the records hold a frame ID, a timestamp and a camera name and nothing else. Say plainly that no person, vehicle or image data exists. Do not imply the system would answer if the data were present.

Test G11 is the one that matters: a legitimate query with an injection appended returns the legitimate intent and ignores the injection, because the injection has nowhere to go.

---

## 14. CLI

`cli.py` runs an interactive loop:

- reads a line
- calls `handle_turn(message, prev_intent, datetime.now())`
- prints the outcome
- updates `prev_intent` per the table in section 12

Print the resolved intent alongside the result. It makes the behaviour legible to anyone reading the submission and makes debugging obvious.

---

## 15. Tests

Split by whether a case needs the model.

**No API call.** Camera resolution (section A), query builder output, result shaping, validation rules like the date swap. These run in milliseconds and cover roughly half the matrix.

**API call.** Extraction, follow-ups, guardrails. Mark these `@pytest.mark.llm` so they can be run separately, and use the frozen clocks. A full run is around 86 calls.

**Throttle the model calls.** The free tier allows 15 requests per minute, and pytest dispatches as fast as it can, so an unthrottled run returns 429s within seconds. Put a minimum interval between calls plus a retry with backoff inside `extract.py`, so the CLI gets the same protection. Around five lines.

While iterating, run the section you are working on rather than the whole suite, and use `pytest --lf` to rerun only what failed. Both cut the call count without adding code.

Follow-up cases are a list of turns sharing one clock, with an assertion after every turn. Asserting only the last turn hides a bug in turn 2 that turn 3 happens to overwrite.

`conftest.py` provides `NOW_A`, `NOW_B`, and a session-scoped database fixture built once.

---

## 16. Benchmark script

`benchmark.py` runs the full matrix against several models and prints a table: model, pass rate on common cases, pass rate on edge cases, total tokens, wall time.

Run Gemini 3.1 Flash Lite and 3.5 Flash Lite first, since both are free. Add an OpenAI model afterwards for a paid comparison column.

This produces the numbers for the README's model choice section. A measured comparison is a stronger justification than an argument from intuition, and the test suite already exists, so the script is thin.

---

## 17. README

Must contain:

- Setup and run instructions, including the database generation step and its runtime.
- The architecture, in a short section: one model call producing a structured object, deterministic code for everything after it, and why the split falls where it does.
- The full convention tables from section 9, since a user cannot predict "last week" versus "past 7 days" otherwise.
- The model choice, with the benchmark numbers behind it.
- The fuzzy match floor and margin, with how they were calibrated.

---

## 18. Build order

Follow these phases in order. Each one ends with passing tests and a commit, so an agent picking the work up mid-build knows exactly where it is.

Maintain `PROGRESS.md` at the repo root. After each phase, append the phase number, what was built, and the test command that proves it. That file is the handover.

| Phase | Build                                                                        | Done when                                                                                      |
| ----- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| 1     | `setup_db.py`, schema, dataset generation                                    | Row count and date span print correctly, rerun appends only missing days                       |
| 2     | `agent/intent.py`: Intent, Extraction, and the four outcome types            | Imports cleanly, fields match section 5                                                        |
| 3     | `agent/cameras.py` plus `tests/test_cameras.py`                              | All of matrix section A passes, no API calls                                                   |
| 4     | `agent/query.py` builder plus `tests/test_query.py`                          | Hand-built Intent objects produce correct SQL and correct row counts against the real database |
| 5     | Result shaping and the summary line                                          | Counts, spans and the capped output render correctly                                           |
| 6     | `agent/extract.py`: schema-enforced model call, prompt, throttling and retry | A single hardcoded message returns a valid Extraction                                          |
| 7     | Validation: camera resolution, date swap, enum check, data bounds            | Wires extraction to a validated Intent                                                         |
| 8     | `agent/session.py` and `cli.py`                                              | A multi-turn conversation runs end to end                                                      |
| 9     | `tests/test_extraction.py`: matrix sections B to E                           | Common query cases pass                                                                        |
| 10    | `tests/test_followups.py` and `test_guardrails.py`: sections F and G         | Follow-ups and guardrails pass                                                                 |
| 11    | `tests/test_responses.py`: sections H and I                                  | Response shapes and clarifications pass                                                        |
| 12    | Threshold calibration script, section J of the matrix                        | Floor and margin chosen from data, hard-coded, recorded                                        |
| 13    | `benchmark.py`                                                               | Comparison table prints                                                                        |
| 14    | `README.md`                                                                  | Contains everything in section 17                                                              |
