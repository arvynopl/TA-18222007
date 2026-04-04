"""
tests/test_renderer.py — Unit tests for modules/feedback/renderer.py.

Strategy:
    - _severity_delta() is a pure function → tested directly.
    - render_* functions call Streamlit → st is patched via unittest.mock so
      no Streamlit server is required (consistent with the project's no-Streamlit
      test convention in conftest.py).
"""

from __future__ import annotations

import sys
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out `streamlit` before any project import touches it.
# This is necessary because renderer.py does `import streamlit as st` at
# module level. Tests must not import Streamlit directly.
# ---------------------------------------------------------------------------

def _make_st_stub() -> types.ModuleType:
    """Return a minimal MagicMock that satisfies renderer.py's st usage."""
    st = MagicMock()
    # Context managers used by renderer: st.expander(...)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    st.expander.return_value = cm
    return st


# Patch streamlit in sys.modules before importing renderer
_st_stub = _make_st_stub()
sys.modules.setdefault("streamlit", _st_stub)


# Now it is safe to import renderer
from modules.feedback.renderer import (  # noqa: E402
    _SEVERITY_LABEL,
    _SEVERITY_ORDER,
    _severity_delta,
)


# ---------------------------------------------------------------------------
# _severity_delta — pure function, no mocking needed
# ---------------------------------------------------------------------------

class TestSeverityDelta:
    def test_improvement(self):
        """Severity drops moderate → mild: arrow ↓ present."""
        result = _severity_delta("moderate", "mild")
        assert "↓" in result

    def test_worsening(self):
        """Severity rises mild → moderate: arrow ↑ present."""
        result = _severity_delta("mild", "moderate")
        assert "↑" in result

    def test_unchanged(self):
        """Same severity → tetap (unchanged) keyword."""
        result = _severity_delta("none", "none")
        assert "tetap" in result

    def test_severe_to_none(self):
        """Best improvement: severe → none."""
        result = _severity_delta("severe", "none")
        assert "↓" in result
        assert _SEVERITY_LABEL["severe"] in result
        assert _SEVERITY_LABEL["none"] in result

    def test_none_to_severe(self):
        """Worst worsening: none → severe."""
        result = _severity_delta("none", "severe")
        assert "↑" in result

    def test_unknown_prev_treated_as_none(self):
        """Unknown prev label index falls back to 0 (none), equal to 'none'."""
        result = _severity_delta("unknown_label", "none")
        # Both map to index 0 → unchanged
        assert "tetap" in result

    def test_all_severity_levels_covered(self):
        """Ensure all valid severity labels produce a non-empty string."""
        for sev in _SEVERITY_ORDER:
            result = _severity_delta("none", sev)
            assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# render_bias_card — patches st, verifies calls
# ---------------------------------------------------------------------------

class TestRenderBiasCard:
    def test_severe_card_expands(self):
        """A severe card should be rendered with expanded=True."""
        from modules.feedback.renderer import render_bias_card
        with patch("modules.feedback.renderer.st") as mock_st:
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            mock_st.expander.return_value = cm

            render_bias_card(
                bias_type="disposition_effect",
                severity="severe",
                explanation="Penjelasan bias.",
                recommendation="Rekomendasi.",
            )
            # expander should be called with expanded=True for non-none severity
            call_kwargs = mock_st.expander.call_args
            assert call_kwargs[1].get("expanded") is True or call_kwargs[0][1] is True

    def test_none_severity_not_expanded(self):
        """A 'none' severity card should be collapsed (expanded=False)."""
        from modules.feedback.renderer import render_bias_card
        with patch("modules.feedback.renderer.st") as mock_st:
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            mock_st.expander.return_value = cm

            render_bias_card(
                bias_type="overconfidence",
                severity="none",
                explanation="Tidak ada bias.",
                recommendation="",
            )
            call_args = mock_st.expander.call_args
            # expanded should be False for severity=="none"
            expanded = (
                call_args[1].get("expanded")
                if call_args[1]
                else call_args[0][1]
            )
            assert expanded is False

    def test_prev_severity_shows_delta(self):
        """When prev_severity is provided, st.caption should be called for delta."""
        from modules.feedback.renderer import render_bias_card
        with patch("modules.feedback.renderer.st") as mock_st:
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            mock_st.expander.return_value = cm

            render_bias_card(
                bias_type="loss_aversion",
                severity="mild",
                explanation="Penjelasan.",
                recommendation="Rekomendasi.",
                prev_severity="moderate",
            )
            mock_st.caption.assert_called()

    def test_no_prev_severity_no_delta(self):
        """When prev_severity is None, st.caption should NOT be called for delta."""
        from modules.feedback.renderer import render_bias_card
        with patch("modules.feedback.renderer.st") as mock_st:
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            mock_st.expander.return_value = cm

            render_bias_card(
                bias_type="overconfidence",
                severity="moderate",
                explanation="Penjelasan.",
                recommendation="Rekomendasi.",
                prev_severity=None,
            )
            mock_st.caption.assert_not_called()


# ---------------------------------------------------------------------------
# _SEVERITY_COLOUR / _SEVERITY_LABEL consistency
# ---------------------------------------------------------------------------

def test_severity_display_maps_complete():
    """All four severity levels must be represented in both display dicts."""
    from modules.feedback.renderer import _SEVERITY_COLOUR, _SEVERITY_LABEL
    for level in ["none", "mild", "moderate", "severe"]:
        assert level in _SEVERITY_COLOUR, f"Missing colour for {level}"
        assert level in _SEVERITY_LABEL, f"Missing label for {level}"


def test_bias_display_name_map_complete():
    """All three bias types must have display names."""
    from modules.feedback.renderer import _BIAS_DISPLAY_NAME
    for bias in ["disposition_effect", "overconfidence", "loss_aversion"]:
        assert bias in _BIAS_DISPLAY_NAME
        assert isinstance(_BIAS_DISPLAY_NAME[bias], str)
        assert len(_BIAS_DISPLAY_NAME[bias]) > 0


# ---------------------------------------------------------------------------
# render_longitudinal_section — patches get_session + st
# ---------------------------------------------------------------------------

class TestRenderLongitudinalSection:
    def test_no_render_for_single_session(self):
        """If user has fewer than 2 sessions, nothing should be rendered."""
        from modules.feedback.renderer import render_longitudinal_section

        mock_summary = {
            "sessions": ["session-1"],
            "trend": {
                "disposition_effect": ["none"],
                "overconfidence": ["mild"],
                "loss_aversion": ["none"],
            },
            "latest": {"disposition_effect": "none", "overconfidence": "mild", "loss_aversion": "none"},
        }

        with patch("modules.feedback.renderer.get_session") as mock_get_sess, \
             patch("modules.feedback.renderer.get_longitudinal_summary", return_value=mock_summary), \
             patch("modules.feedback.renderer.st") as mock_st:
            # Set up context manager for get_session()
            sess_cm = MagicMock()
            sess_cm.__enter__ = MagicMock(return_value=MagicMock())
            sess_cm.__exit__ = MagicMock(return_value=False)
            mock_get_sess.return_value = sess_cm

            render_longitudinal_section(user_id=1)

            # With < 2 sessions, no subheader or table should be rendered
            mock_st.subheader.assert_not_called()
            mock_st.table.assert_not_called()

    def test_renders_table_for_multiple_sessions(self):
        """With 2+ sessions, a table should be rendered."""
        from modules.feedback.renderer import render_longitudinal_section

        mock_summary = {
            "sessions": ["session-1", "session-2"],
            "trend": {
                "disposition_effect": ["none", "mild"],
                "overconfidence": ["none", "moderate"],
                "loss_aversion": ["none", "none"],
            },
            "latest": {"disposition_effect": "mild", "overconfidence": "moderate", "loss_aversion": "none"},
        }

        with patch("modules.feedback.renderer.get_session") as mock_get_sess, \
             patch("modules.feedback.renderer.get_longitudinal_summary", return_value=mock_summary), \
             patch("modules.feedback.renderer.st") as mock_st:
            sess_cm = MagicMock()
            sess_cm.__enter__ = MagicMock(return_value=MagicMock())
            sess_cm.__exit__ = MagicMock(return_value=False)
            mock_get_sess.return_value = sess_cm

            render_longitudinal_section(user_id=1)

            mock_st.table.assert_called_once()
            table_data = mock_st.table.call_args[0][0]
            assert len(table_data) == 2  # one row per session
