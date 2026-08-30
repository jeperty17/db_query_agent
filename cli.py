"""Interactive loop. The only place datetime.now() is called. See SPEC.md section 14."""
from datetime import datetime

from agent.intent import Clarification, Intent, OutOfRange, QueryResult, Refusal
from agent.query import format_summary
from agent.session import handle_turn, next_state


def _print_outcome(outcome):
    if isinstance(outcome, QueryResult):
        print(format_summary(outcome))
        for frame_id, dt, camera in outcome.rows[:10]:
            print(f"  {frame_id:>8}  {dt}  {camera}")
    elif isinstance(outcome, Clarification):
        print(f"Clarify: {outcome.question}")
    elif isinstance(outcome, Refusal):
        print(f"Refused: {outcome.message}")
    elif isinstance(outcome, OutOfRange):
        req_from, req_to = outcome.requested
        avail_from, avail_to = outcome.available
        print(f"Out of range: requested {req_from}..{req_to}, data covers {avail_from}..{avail_to}")


def main():
    prev = None
    print("Ask about CCTV frames. Ctrl-D to quit.")
    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        outcome = handle_turn(message, prev, datetime.now())
        prev = next_state(prev, outcome)
        print(f"intent: {prev}")
        _print_outcome(outcome)


if __name__ == "__main__":
    main()
