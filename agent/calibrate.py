"""Reproducible fuzzy-camera threshold calibration (test-matrix.md section J)."""
from rapidfuzz import fuzz

from agent.cameras import _STEMS

TYPO_VARIANTS = [
    "pan isalnd", "ayer raja", "east coas", "centarl", "tampines expersway",
    "kallang paya lebar", "seletar expwy", "bukit timha", "kranjee", "marina coatal",
]
NON_CAMERAS = ["Jurong", "Serangoon", "Woodlands", "Changi"]


def best_two(phrase: str) -> tuple[float, float]:
    scores = sorted((fuzz.WRatio(phrase, stem) for stem in _STEMS.values()), reverse=True)
    return scores[0], scores[1]


def main() -> None:
    print("phrase\tbest\trunner-up")
    for phrase in TYPO_VARIANTS + NON_CAMERAS:
        best, runner_up = best_two(phrase)
        print(f"{phrase}\t{best:.1f}\t{runner_up:.1f}")
    print("Chosen floor=70, margin=10 (see README).")


if __name__ == "__main__":
    main()
