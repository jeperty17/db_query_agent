# CCTV frame query agent

This is a deliberately small natural-language interface over generated CCTV
frame records. One Gemini call returns an `Extraction` object. Deterministic
Python resolves its camera phrases, validates it, builds a parameter-bound
SQLite query, and shapes the response. The model never emits SQL or accesses the
database.

## Setup and run

```sh
python3 -m pip install -r requirements.txt
printf 'GEMINI_API_KEY=your-key\n' > .env
python3 setup_db.py
python3 cli.py
```

Dataset generation creates one frame per camera every five minutes from
2026-01-01 through today. It takes a few seconds on a typical laptop and is
idempotent: later runs append only missing dates. The generated `frames.db` is
ignored by Git. The SQLite connection uses `mode=ro`, so writes fail at the
driver.

Run deterministic tests with `python3 -m pytest -m 'not llm'`; run model tests
with `python3 -m pytest -m llm`. To compare models, prefix the same command:
`GEMINI_MODEL=gemini-3.5-flash-lite python3 -m pytest -m llm`.

## Conventions

All ranges are inclusive. `last`/`this` plus a calendar unit means that calendar
unit; a numbered period is rolling from today; weeks run Monday–Sunday; numeric
dates use DD/MM; the first week is days 1–7 and the last week is the final seven
days; `last Tuesday` means the most recent Tuesday before today.

| Time phrase | Range |
| --- | --- |
| early morning | 00:00–05:59 |
| morning | 06:00–11:59 |
| lunch | 12:00–13:59 |
| afternoon | 12:00–16:59 |
| evening | 17:00–19:59 |
| night | 20:00–23:59 |

A bare hour is its whole clock hour (for example, `3pm` is 15:00–15:59).
Overnight ranges are evaluated inside each date, rather than extending the date
range.

## Safety and camera matching

Every query value is a SQLite bound parameter. The query builder interpolates
only the count of `?` placeholders. The structured object has no mutation verb,
and the database is read-only. Unsupported, sensitive, unrelated, and mutation
requests are refused while clarifications preserve conversational state.

Camera names are lowercased, stripped of punctuation and trailing road words,
then matched against ten stems. Acronyms must be exact. The score floor is
70 with a 10-point winner/runner-up margin, calibrated against the accepted and
rejected phrases in the test matrix rather than a separate, arbitrary list of
typos and non-camera names: real stems score 76 or better against their own
stem, decoys (Jurong, Serangoon, the expressway, garbled acronyms) top out at
60, and 70/10 sits in that gap. `tests/test_cameras.py` holds every one of
those cases, so a threshold change that breaks the calibration fails the suite.

## Model choice

The default is `gemini-3.1-flash-lite`, chosen for availability rather than
capability: it is what the free Gemini API tier gives me, so it is what the
whole test matrix was actually run against. Nothing in the code assumes it —
`GEMINI_MODEL` overrides the default, and the free tier's 500-requests-per-day
quota is counted per model, which is worth knowing when a full `llm` run costs
roughly 120 calls.

The task suits a small model: constrained structured extraction into a fixed
schema, not something that benefits from a multi-step agent. The client uses
the SDK's Pydantic response-schema support, a five-second minimum call interval,
retries, and a request timeout.

The prompt was hardened against 3.1 and 3.5 Flash Lite in turn, and the two
disagreed enough to be useful: 3.5 dropped `time_to` on named windows, 3.1
clarified instead of leaving an unmentioned axis unfiltered, and each exposed
wording the other tolerated. Every fix went in as a general rule, so the prompt
is stricter than either model alone required. Comparing models needs no
tooling beyond a `GEMINI_MODEL` prefix on the same `pytest -m llm` command; no
invented benchmark figures are reported.
