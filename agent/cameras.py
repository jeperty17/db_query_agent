"""Camera phrase -> acronym resolution. Pure function, no API call.

See SPEC.md section 6.
"""
import re

from rapidfuzz import fuzz

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

ROAD_WORDS = {"expressway", "highway", "parkway", "expwy", "expy", "road"}

# Calibrated in agent/calibrate.py (SPEC.md section J / phase 12): real-camera
# stems score >=76 against their own stem, decoys (Jurong, Serangoon,
# Woodlands, Changi, garbled acronyms) top out at <=60. 70/10 sits in the gap
# with margin either side. Recorded in README.md.
SCORE_FLOOR = 70
SCORE_MARGIN = 10


def _normalize(phrase):
    phrase = phrase.lower()
    phrase = re.sub(r"[^a-z0-9\s]", " ", phrase)
    return re.sub(r"\s+", " ", phrase).strip()


def _strip_road_word(stem):
    words = stem.split()
    if words and words[-1] in ROAD_WORDS:
        words = words[:-1]
    return " ".join(words)


_STEMS = {acronym: _strip_road_word(_normalize(name)) for acronym, name in CAMERAS.items()}


def resolve_camera(phrase):
    normalized = _normalize(phrase)

    acronym = normalized.replace(" ", "").upper()
    if acronym in CAMERAS:
        return acronym

    stem = _strip_road_word(normalized)
    ranked = sorted(
        ((code, fuzz.WRatio(stem, s)) for code, s in _STEMS.items()),
        key=lambda item: -item[1],
    )
    best_code, best_score = ranked[0]
    runner_score = ranked[1][1]
    if best_score >= SCORE_FLOOR and (best_score - runner_score) >= SCORE_MARGIN:
        return best_code
    return None
