"""
tests/test_layout.py — Unit tests for modules/utils/layout.py.

The module under test imports ``streamlit as st`` at module load. Rather than
race other tests for sys.modules ownership, this file imports the layout
module and then swaps its ``st`` attribute with a MagicMock per test (via the
autouse fixture). This is robust regardless of whether real Streamlit is
already present in sys.modules.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from unittest.mock import call

from modules.utils import layout


def _make_st_stub() -> MagicMock:
    """Return a MagicMock satisfying the layout helpers' usage of ``st``."""
    st = MagicMock()
    st.session_state = {}

    def _columns(spec):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock(name=f"col-{i}") for i in range(n)]

    st.columns.side_effect = _columns
    st.container.side_effect = lambda: MagicMock(name="container")

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    st.expander.return_value = cm

    st.context = types.SimpleNamespace(viewport=types.SimpleNamespace(width=None))
    return st


@pytest.fixture(autouse=True)
def stub_st(monkeypatch):
    """Replace ``layout.st`` with a fresh MagicMock for each test."""
    stub = _make_st_stub()
    monkeypatch.setattr(layout, "st", stub)
    yield stub


# ---------------------------------------------------------------------------
# is_mobile()
# ---------------------------------------------------------------------------
class TestIsMobile:
    def test_default_is_desktop_when_no_state_set(self, stub_st):
        assert layout.is_mobile() is False

    def test_override_mobile_forces_true(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        assert layout.is_mobile() is True

    def test_override_desktop_forces_false_even_with_narrow_viewport(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "desktop"
        stub_st.context = types.SimpleNamespace(
            viewport=types.SimpleNamespace(width=320)
        )
        assert layout.is_mobile() is False

    def test_override_auto_falls_through_to_autodetect(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "auto"
        stub_st.context = types.SimpleNamespace(
            viewport=types.SimpleNamespace(width=400)
        )
        assert layout.is_mobile() is True

    def test_legacy_mobile_mode_flag_still_honored(self, stub_st):
        stub_st.session_state["mobile_mode"] = True
        assert layout.is_mobile() is True

    def test_autodetect_below_breakpoint(self, stub_st):
        stub_st.context = types.SimpleNamespace(
            viewport=types.SimpleNamespace(width=640)
        )
        assert layout.is_mobile() is True

    def test_autodetect_at_breakpoint_is_desktop(self, stub_st):
        stub_st.context = types.SimpleNamespace(
            viewport=types.SimpleNamespace(width=layout.MOBILE_BREAKPOINT_PX)
        )
        assert layout.is_mobile() is False

    def test_autodetect_handles_missing_attribute(self, stub_st):
        stub_st.context = types.SimpleNamespace()  # no .viewport
        assert layout.is_mobile() is False


# ---------------------------------------------------------------------------
# responsive_columns()
# ---------------------------------------------------------------------------
class TestResponsiveColumns:
    def test_desktop_returns_n_cells(self, stub_st):
        cells = layout.responsive_columns(4)
        assert len(cells) == 4

    def test_mobile_n_mobile_1_returns_n_cells_via_containers(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        cells = layout.responsive_columns(3)
        assert len(cells) == 3

    def test_mobile_n_mobile_2_returns_4_cells(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        cells = layout.responsive_columns(4, n_mobile=2)
        assert len(cells) == 4

    def test_desktop_n_mobile_2_returns_4_cells(self, stub_st):
        cells = layout.responsive_columns(4, n_mobile=2)
        assert len(cells) == 4

    def test_weighted_spec_desktop(self, stub_st):
        cells = layout.responsive_columns([5, 1])
        assert len(cells) == 2

    def test_weighted_spec_mobile_stacks(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        cells = layout.responsive_columns([5, 1], n_mobile=1)
        assert len(cells) == 2

    def test_invalid_n_mobile_raises(self, stub_st):
        with pytest.raises(ValueError):
            layout.responsive_columns(3, n_mobile=0)


# ---------------------------------------------------------------------------
# responsive_tabs()
# ---------------------------------------------------------------------------
class TestResponsiveTabs:
    def test_desktop_delegates_to_st_tabs(self, stub_st):
        """Desktop mode returns whatever st.tabs returns."""
        mock_tabs = [MagicMock(name=f"tab-{i}") for i in range(3)]
        stub_st.tabs.return_value = mock_tabs
        result = layout.responsive_tabs(["A", "B", "C"])
        stub_st.tabs.assert_called_once_with(["A", "B", "C"])
        assert result is mock_tabs

    def test_desktop_returns_correct_length(self, stub_st):
        stub_st.tabs.return_value = [MagicMock() for _ in range(4)]
        result = layout.responsive_tabs(["W", "X", "Y", "Z"])
        assert len(result) == 4

    def test_mobile_returns_expanders_not_tabs(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        layout.responsive_tabs(["A", "B", "C"])
        stub_st.tabs.assert_not_called()
        assert stub_st.expander.call_count == 3

    def test_mobile_returns_correct_length(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        result = layout.responsive_tabs(["A", "B", "C"])
        assert len(result) == 3

    def test_mobile_first_expander_expanded(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        call_log: list[tuple] = []

        def _expander(label, expanded=False):
            call_log.append((label, expanded))
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        stub_st.expander.side_effect = _expander
        layout.responsive_tabs(["Alpha", "Beta", "Gamma"])
        assert call_log[0] == ("Alpha", True)
        assert call_log[1] == ("Beta", False)
        assert call_log[2] == ("Gamma", False)

    def test_mobile_single_label_expanded(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        call_log: list[tuple] = []

        def _expander(label, expanded=False):
            call_log.append((label, expanded))
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        stub_st.expander.side_effect = _expander
        layout.responsive_tabs(["Solo"])
        assert call_log == [("Solo", True)]

    def test_empty_labels_returns_empty(self, stub_st):
        stub_st.tabs.return_value = []
        result = layout.responsive_tabs([])
        assert result == []


# ---------------------------------------------------------------------------
# render_viewport_override + deprecated render_mobile_toggle
# ---------------------------------------------------------------------------
class TestViewportOverride:
    def test_initializes_pref_to_auto(self, stub_st):
        layout.render_viewport_override()
        assert stub_st.session_state["cdt_viewport_pref"] == "auto"

    def test_does_not_overwrite_existing_pref(self, stub_st):
        stub_st.session_state["cdt_viewport_pref"] = "mobile"
        layout.render_viewport_override()
        assert stub_st.session_state["cdt_viewport_pref"] == "mobile"

    def test_render_mobile_toggle_delegates_and_warns_once(self, stub_st, caplog):
        with caplog.at_level("WARNING", logger=layout.logger.name):
            layout.render_mobile_toggle()
            layout.render_mobile_toggle()
        deprecation_msgs = [
            r for r in caplog.records if "deprecated" in r.getMessage()
        ]
        assert len(deprecation_msgs) == 1
        assert stub_st.session_state["cdt_viewport_pref"] == "auto"
