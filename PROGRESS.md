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

