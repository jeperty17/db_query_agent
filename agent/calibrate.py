"""Dev tool: checks that the camera-matching settings are tuned correctly."""
from rapidfuzz import fuzz

from agent.camera_cases import CAMERA_CASES
from agent.cameras import CAMERAS, _STEMS, _normalize, _strip_road_word


def best_two(phrase):
    stem = _strip_road_word(_normalize(phrase))
    scores = sorted((fuzz.WRatio(stem, camera_stem) for camera_stem in _STEMS.values()), reverse=True)
    return scores[0], scores[1]


def main():
    # Exact acronyms do not reach fuzzy matching, so omit them from this report.
    fuzzy_cases = [
        (case_id, phrase, expected)
        for case_id, phrase, expected in CAMERA_CASES
        if _normalize(phrase).replace(" ", "").upper() not in CAMERAS
    ]
    print("case\texpected\tbest\trunner-up")
    for case_id, phrase, expected in fuzzy_cases:
        best, runner_up = best_two(phrase)
        expectation = expected or "reject"
        print(f"{case_id}\t{expectation}\t{best:.1f}\t{runner_up:.1f}")
    print("Chosen floor=70, margin=10 (see README).")


if __name__ == "__main__":
    main()
