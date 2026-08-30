"""Test matrix section A: camera resolution. No API calls.

resolve_camera takes an isolated camera-phrase span (what Extraction.camera_phrases
would hold), not a full sentence, per SPEC.md section 6.
"""
import pytest

from agent.camera_cases import CAMERA_CASES
from agent.cameras import resolve_camera

@pytest.mark.parametrize("case_id,phrase,expected", CAMERA_CASES, ids=[c[0] for c in CAMERA_CASES])
def test_resolve_camera(case_id, phrase, expected):
    assert resolve_camera(phrase) == expected


def test_A17_multiple_cameras():
    assert [resolve_camera("PIE"), resolve_camera("CTE")] == ["PIE", "CTE"]
