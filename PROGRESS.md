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

