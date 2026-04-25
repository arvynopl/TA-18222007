"""tests/test_interaction_teaser.py — teaser gating for sessions 1–4 vs 5+.

We invoke the gating helper directly to avoid Streamlit runtime deps; the
teaser has a dedicated entry point `render_interaction_teaser`.
"""

import pytest

from modules.feedback import renderer


def test_threshold_constant():
    assert renderer.INTERACTION_TEASER_THRESHOLD_SESSIONS == 5


def test_translate_top_correlation_returns_none_for_empty():
    assert renderer._translate_top_correlation({}) is None
    assert renderer._translate_top_correlation(None) is None


def test_translate_top_correlation_picks_highest_magnitude():
    scores = {"ocs_dei": 0.71, "ocs_lai": -0.30, "dei_lai": 0.50}
    narrative = renderer._translate_top_correlation(scores)
    assert narrative is not None
    assert "0.71" in narrative or "+0.71" in narrative
    assert "Keyakinan Berlebih" in narrative  # top pair = ocs_dei


def test_translate_top_correlation_weak_label_for_small_r():
    scores = {"ocs_dei": 0.15, "ocs_lai": -0.10, "dei_lai": 0.05}
    narrative = renderer._translate_top_correlation(scores)
    assert narrative is not None
    assert "lemah" in narrative.lower()


def test_translate_top_correlation_direction_sign():
    pos = renderer._translate_top_correlation({"ocs_dei": 0.6, "ocs_lai": None, "dei_lai": None})
    neg = renderer._translate_top_correlation({"ocs_dei": -0.6, "ocs_lai": None, "dei_lai": None})
    assert pos and neg
    assert "ikut meningkat" in pos
    assert "justru menurun" in neg
