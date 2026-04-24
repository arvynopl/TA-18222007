"""tests/test_dual_ring_radar.py — dual-ring radar chart contract."""

import plotly.graph_objects as go
import pytest

from config import DEI_SEVERE, LAI_EMA_CEILING, LAI_SEVERE, OCS_SEVERE
from modules.utils.ui_helpers import (
    _normalised_scientific_thresholds, build_dual_radar_chart,
)


def _trace_by_name(fig: go.Figure, name: str):
    matches = [t for t in fig.data if t.name == name]
    assert matches, f"expected trace named {name!r}, got {[t.name for t in fig.data]}"
    return matches[0]


def test_chart_contains_scientific_watchpoint_trace():
    fig = build_dual_radar_chart(
        current_scores={"dei": 0.1, "ocs": 0.2, "lai": 0.3},
        avg_scores={"dei": 0.2, "ocs": 0.3, "lai": 0.4},
    )
    sci = _trace_by_name(fig, "Titik Waspada Ilmiah")
    # First 3 radii should match config thresholds (closed polygon wraps).
    r = list(sci.r)[:3]
    expected = [DEI_SEVERE, OCS_SEVERE, min(LAI_SEVERE / LAI_EMA_CEILING, 1.0)]
    assert r == pytest.approx(expected)


def test_chart_contains_personal_watchpoint_trace():
    fig = build_dual_radar_chart(
        current_scores={"dei": 0.1, "ocs": 0.2, "lai": 0.3},
        avg_scores={"dei": 0.2, "ocs": 0.3, "lai": 0.4},
        personal_thresholds={"dei": 0.45, "ocs": 0.55, "lai": 0.6},
        personal_threshold_is_fallback=False,
    )
    pers = _trace_by_name(fig, "Titik Waspada Pribadi")
    assert list(pers.r)[:3] == pytest.approx([0.45, 0.55, 0.6])


def test_personal_watchpoint_label_changes_on_fallback():
    fig = build_dual_radar_chart(
        current_scores={"dei": 0.0, "ocs": 0.0, "lai": 0.0},
        avg_scores={"dei": 0.0, "ocs": 0.0, "lai": 0.0},
        personal_threshold_is_fallback=True,
    )
    names = [t.name for t in fig.data]
    assert "Titik Waspada Pribadi (data belum cukup)" in names
    assert "Titik Waspada Pribadi" not in names


def test_no_hardcoded_half_threshold_label():
    fig = build_dual_radar_chart(
        current_scores={"dei": 0.0, "ocs": 0.0, "lai": 0.0},
        avg_scores={"dei": 0.0, "ocs": 0.0, "lai": 0.0},
    )
    names = [t.name for t in fig.data]
    assert "Ambang Batas Perhatian" not in names, (
        "v6 must replace the arbitrary 0.5 ring with evidence-based rings."
    )


def test_scientific_thresholds_match_config():
    exp = {
        "dei": float(DEI_SEVERE),
        "ocs": float(OCS_SEVERE),
        "lai": min(float(LAI_SEVERE) / float(LAI_EMA_CEILING), 1.0),
    }
    assert _normalised_scientific_thresholds() == pytest.approx(exp)
