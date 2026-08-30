"""Test matrix section A: camera resolution. No API calls.

resolve_camera takes an isolated camera-phrase span (what Extraction.camera_phrases
would hold), not a full sentence, per SPEC.md section 6.
"""
import pytest

from agent.cameras import resolve_camera

# (matrix id, phrase span, expected acronym or None for Clarification)
CASES = [
    ("A1", "CTE", "CTE"),
    ("A2", "Central Expressway", "CTE"),
    ("A3", "cte", "CTE"),
    ("A4", "Kranji Highway", "KJE"),
    ("A5", "Tampines Parkway", "TPE"),
    ("A6", "East Coast", "ECP"),
    ("A7", "Tampines", "TPE"),
    ("A8", "Tampines Expresway", "TPE"),      # typo
    ("A9", "Kranjee Expressway", "KJE"),      # typo
    ("A10", "Kallang-Paya Lebar Expressway", "KPE"),
    ("A11", "Kallang Paya Lebar", "KPE"),
    ("A12", "Marina Coastal", "MCE"),
    ("A13", "Pan Island", "PIE"),
    ("A14", "TPY", None),                     # acronym-shaped but invalid
    ("A15", "KJE", "KJE"),                    # valid acronym resolves as written
    ("A16", "Jurong Expressway", None),
    ("A20", "the expressway", None),
]


@pytest.mark.parametrize("case_id,phrase,expected", CASES, ids=[c[0] for c in CASES])
def test_resolve_camera(case_id, phrase, expected):
    assert resolve_camera(phrase) == expected


def test_A17_multiple_cameras():
    assert [resolve_camera("PIE"), resolve_camera("CTE")] == ["PIE", "CTE"]
