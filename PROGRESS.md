# Progress

## Phase 1: setup_db.py, schema, dataset generation

Built `setup_db.py`. Single `frames` table (schema per SPEC.md section 4) plus the
two indexes. Generates one row per camera every 5 minutes from 2026-01-01 through
today, via `executemany` inside one transaction. Idempotent: reruns read
`MAX(frame_date)` and only append missing days (empty-table case falls out of the
same `MAX()` query returning `NULL`, so there's no separate "does the db exist"
branch).

`date.today()` is called only under `if __name__ == "__main__"`, mirroring
cli.py's role as the one real-clock entry point — `generate()` itself takes
`today` as a parameter.

Proof:
```
$ python3 setup_db.py
696960 rows, 2026-01-01 to 2026-08-30
$ python3 setup_db.py   # rerun, idempotent
696960 rows, 2026-01-01 to 2026-08-30   # 0.08s, no new rows
```
242 days * 2880 rows/day (10 cameras * 288 samples/day) = 696,960. Matches.

Decision: `frames.db` and `__pycache__/` added to `.gitignore` — a 65MB generated
artifact doesn't belong in git; `setup_db.py` regenerates it in ~2s.

## Phase 2: agent/intent.py

`Intent` and `Extraction` as pydantic models (SPEC.md section 5 and 7, verbatim
field lists — pydantic gives the Gemini SDK schema enforcement on `Extraction`
later). The four outcome types (`QueryResult`, `Clarification`, `Refusal`,
`OutOfRange`, section 12) are plain `@dataclass`es, not pydantic — they're
internal containers built from Python data, never parsed from JSON or the
network, so pydantic's validation buys nothing there. `Outcome` is a `Union`
type alias of the four, for use in query.py/session.py signatures.

Proof:
```
$ python3 -c "from agent.intent import Intent, Extraction, QueryResult, Clarification, Refusal, OutOfRange, Outcome; ..."
OK
```

## Phase 3: agent/cameras.py + tests/test_cameras.py (matrix section A)

`resolve_camera(phrase)`: normalize (lowercase, punctuation -> space, collapse
whitespace) -> exact acronym check -> strip trailing road word -> `rapidfuzz.fuzz.WRatio`
against the ten stems (derived from `CAMERAS`, not hand-duplicated) -> accept only if
top score clears a floor and beats the runner-up by a margin.

Chose floor=70, margin=10 by scoring the matrix's real cases (typos included, e.g.
"kranjee" -> KJE 76.9) against decoys (Jurong, "tpy", "the", Serangoon, Woodlands,
Changi, Sengkang — all <=60 top score) with a small ad-hoc script — see the ranked
score dump in this session's shell history. This *is* the section J calibration; a
formal `agent/calibrate.py` gets built at phase 12 mainly to make the process
reproducible and to document it in the README, not to re-derive different numbers.

Test file covers matrix A1-A16, A20 (18 parametrized cases) as isolated camera-phrase
spans, matching resolve_camera's actual signature — a full sentence like "show me CTE
frames" is not what the function receives; the model extracts the span first (phase 6+).
A17 (multi-camera) gets its own test. A18/A19 (empty camera_phrases -> `[]`) and A21
(validator rejects a hallucinated camera) aren't resolve_camera behavior — they belong
to extraction/validation, deferred to phases 7/9.

Proof:
```
$ python3 -m pytest tests/test_cameras.py -v
18 passed in 0.03s
```

## Phase 4: agent/query.py builder + tests/test_query.py

`build_query(intent)` is section 11's code verbatim: one clause per present
field, every value a bound parameter, the only f-strings are the `?`
placeholder scaffolding derived from list length. `connect()` opens
`file:frames.db?mode=ro` (read-only guardrail, non-negotiable #3).

Kept result-shaping (notes, capping, the summary line) out of this file —
that's phase 5's job per the build order, not phase 4's.

`tests/conftest.py` added: `NOW_A`/`NOW_B` frozen clocks and a session-scoped
`db_conn` fixture (calls `setup_db.generate` — idempotent, so it's a no-op if
`frames.db` is already current).

Test file hand-builds Intent objects and checks both the generated SQL text
and real row counts against `frames.db`:
- C1 boundary (08:00-10:00 inclusive on one day/camera = 25 rows, not 24)
- C10 overnight OR-clause stays within one day (97 rows), doesn't shift date_to
- C11 sub-5-minute window (10:01-10:03) legitimately returns 0 rows
- D7 origin check: `days_of_week=[1]` (Tuesday, Python-Monday-0 convention)
  returns the full 2880 rows on 2026-08-25 (a Tuesday) and 0 on 2026-08-24
  (a Monday) — this is the exact SQLite-vs-Python weekday() bug the spec
  warns about, caught by asserting on a Monday explicitly.

Proof:
```
$ python3 -m pytest tests/test_query.py -v
11 passed in 1.19s
```

## Phase 5: result shaping and the summary line

Added to `agent/query.py`: `run_query(conn, intent) -> QueryResult` (COUNT(*)
with the same WHERE, capped 50-row sample, notes for capping / zero-rows /
partial dataset coverage) and `format_summary(result) -> str` (the plain-English
line, e.g. `"1,247 frames | CTE | 24-30 Aug 2026 | 08:00-10:00 | Tuesdays only"`,
omitting any axis that isn't filtered).

`run_query` derives the COUNT query's WHERE clause by slicing the string
`build_query` already produced (`sql[len(_SELECT):-len(" ORDER BY datetime")]`)
rather than rebuilding it — one clause-building path, not two that could drift.
The sliced-out substring is only ever `""` or `" WHERE camera IN (?,?) AND ..."`
built entirely from bound-parameter placeholders and fixed column names, so it
carries no user text.

Days-of-week formatting special-cases `[5,6]` -> "Weekends" and `[0,1,2,3,4]` ->
"Weekdays" (matrix D2/D3 read naturally that way); anything else joins plural
day names.

Proof:
```
$ python3 -m pytest tests/test_query.py -v
16 passed in 1.17s
```
Covers: sample capping + total note, B14 partial-coverage note ("...30 Aug
2026..." when requesting through 08-31 but data ends 08-30), zero-rows-says-so
(C11-style), and format_summary with all axes set vs. none.

## Phase 6: agent/extract.py (model call, prompt, throttling, retry)

Verified the `google-genai` SDK's structured-output path first with a scratch
call: `GenerateContentConfig(response_mime_type="application/json",
response_schema=Extraction)` + `response.parsed` returns an already-parsed
`Extraction` instance directly — no manual JSON parsing needed.

`extract(message, prev, now) -> Extraction`: builds the system prompt once at
module load (cameras, date/time convention tables, carry-forward and
refuse/clarify instructions — kept to one paragraph per topic, no
chain-of-thought scaffolding), sends current datetime + serialized previous
intent + the message as the user turn, and returns `response.parsed`.

Throttling/retry (SPEC.md section 15's "~5 lines"): a module-level
`_last_call` timestamp enforces `MIN_INTERVAL = 4.1s` between calls (free tier
= 15 req/min), plus up to 3 attempts with exponential backoff on any
exception (covers 429s).

`.env` isn't parsed by a dependency (only 4 allowed: pydantic, rapidfuzz,
google-genai, pytest) — a five-line manual loader reads `GEMINI_API_KEY=`
from `.env` into `os.environ` if not already set.

`now` is a required parameter, never read from the clock internally — matches
non-negotiable #4.

Verified a hallucinated substitution risk: with a minimal test prompt, the
model returned `camera_phrases=["Central Expressway"]` for input "CTE" (an
expansion, not a verbatim copy). Not a correctness bug — `resolve_camera`
already handles full names via fuzzy match — but the real system prompt
explicitly says "copy the camera span verbatim" to stay closer to spec intent.

Proof:
```
$ python3 -c "from agent.extract import extract; from datetime import datetime; print(extract('show me frames from CTE today', None, datetime(2026,8,30,14,30)))"
action='query' camera_phrases=['CTE'] date_from=date(2026,8,30) date_to=date(2026,8,30) time_from=None time_to=None days_of_week=None message=None
```

