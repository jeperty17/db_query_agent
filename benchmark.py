"""Run the test suite for a selected Gemini model and print a compact score."""
import os
import subprocess
import sys
import time


def main() -> None:
    models = sys.argv[1:] or ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    print("model\tpassed\tfailed\twall_s")
    for model in models:
        started = time.monotonic()
        env = os.environ | {"GEMINI_MODEL": model}
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-m", "llm"], text=True,
            capture_output=True, env=env,
        )
        elapsed = time.monotonic() - started
        summary = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else "no pytest output"
        print(f"{model}\t{summary}\t{elapsed:.1f}")


if __name__ == "__main__":
    main()
