"""
tests/test_ui_helpers.py — Smoke tests for the mobile-aware chart theme.

Confirms that ``apply_chart_theme`` produces a smaller height and a different
legend placement when ``is_mobile()`` returns True. The test does not assert
visual fidelity; Plotly outputs are not inspected pixel-for-pixel anywhere in
the suite.
"""

from __future__ import annotations

import plotly.graph_objects as go
import pytest

from modules.utils import layout, ui_helpers


@pytest.fixture()
def force_desktop(monkeypatch):
    monkeypatch.setattr(layout, "is_mobile", lambda: False)


@pytest.fixture()
def force_mobile(monkeypatch):
    monkeypatch.setattr(layout, "is_mobile", lambda: True)


class TestApplyChartTheme:
    def test_desktop_keeps_requested_height(self, force_desktop):
        fig = go.Figure()
        ui_helpers.apply_chart_theme(fig, height=400)
        assert fig.layout.height == 400

    def test_mobile_height_lower_than_desktop(self, force_mobile):
        fig_mobile = go.Figure()
        ui_helpers.apply_chart_theme(fig_mobile, height=400)
        assert fig_mobile.layout.height < 400
        assert fig_mobile.layout.height >= 260  # the floor

    def test_mobile_explicit_mobile_height_wins(self, force_mobile):
        fig = go.Figure()
        ui_helpers.apply_chart_theme(fig, height=400, mobile_height=300)
        assert fig.layout.height == 300

    def test_mobile_height_floor_of_260(self, force_mobile):
        fig = go.Figure()
        ui_helpers.apply_chart_theme(fig, height=200)
        # 200 * 0.7 = 140, floor brings it back up to 260
        assert fig.layout.height == 260

    def test_mobile_legend_top_increases_top_margin(self, force_mobile):
        fig = go.Figure()
        ui_helpers.apply_chart_theme(fig, height=400, mobile_legend="top")
        assert fig.layout.margin.t == 70

    def test_mobile_legend_hide_disables_legend(self, force_mobile):
        fig = go.Figure()
        ui_helpers.apply_chart_theme(fig, height=400, mobile_legend="hide")
        assert fig.layout.showlegend is False

    def test_explicit_margin_override_wins(self, force_mobile):
        fig = go.Figure()
        ui_helpers.apply_chart_theme(
            fig, height=400, margin=dict(l=5, r=5, t=99, b=5)
        )
        assert fig.layout.margin.t == 99


class TestSeverityGauge:
    def test_mobile_gauge_height_smaller(self, force_mobile):
        fig = ui_helpers.build_severity_gauge(0.5, 1.0, "Test", "moderate")
        assert fig.layout.height == 160

    def test_desktop_gauge_height_unchanged(self, force_desktop):
        fig = ui_helpers.build_severity_gauge(0.5, 1.0, "Test", "moderate")
        assert fig.layout.height == 200


class TestRadarCharts:
    def test_mobile_radar_height_smaller(self, force_mobile):
        fig = ui_helpers.build_radar_chart({"overconfidence": 0.4, "disposition": 0.3, "loss_aversion": 0.5})
        assert fig.layout.height == 300

    def test_desktop_radar_height_unchanged(self, force_desktop):
        fig = ui_helpers.build_radar_chart({"overconfidence": 0.4, "disposition": 0.3, "loss_aversion": 0.5})
        assert fig.layout.height == 350

    def test_mobile_dual_radar_height_and_legend_y(self, force_mobile):
        fig = ui_helpers.build_dual_radar_chart(
            current_scores={"dei": 0.3, "ocs": 0.4, "lai": 0.2},
            avg_scores={"dei": 0.25, "ocs": 0.35, "lai": 0.25},
        )
        assert fig.layout.height == 360
        assert fig.layout.legend.y == -0.45

    def test_desktop_dual_radar_height_unchanged(self, force_desktop):
        fig = ui_helpers.build_dual_radar_chart(
            current_scores={"dei": 0.3, "ocs": 0.4, "lai": 0.2},
            avg_scores={"dei": 0.25, "ocs": 0.35, "lai": 0.25},
        )
        assert fig.layout.height == 440
        assert fig.layout.legend.y == -0.32
