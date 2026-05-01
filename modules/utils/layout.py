"""
modules/utils/layout.py — Mobile-aware layout helpers for the CDT app.

Auto-detects mobile viewports via ``st.context.viewport.width`` (Streamlit
≥1.32) so UAT participants do not have to flip a manual toggle. A small
"Pengaturan tampilan" override lives in the app header for runtimes where the
server-side viewport probe is unavailable, or when a tester wants to force a
particular layout.

Public API stays stable: ``is_mobile()`` returns a bool, ``responsive_columns``
returns a list of column-like contexts. The legacy ``render_mobile_toggle``
remains as a deprecated wrapper.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import streamlit as st

logger = logging.getLogger(__name__)

# Legacy bool flag — predates the auto-detect/override architecture. Kept so
# any caller that still writes ``st.session_state["mobile_mode"] = True``
# continues to force the mobile layout.
_MOBILE_FLAG = "mobile_mode"

# Three-way override: "auto" (default), "mobile", or "desktop". When "auto",
# is_mobile() consults st.context.viewport.
_VIEWPORT_PREF_KEY = "cdt_viewport_pref"

# Internal: tracks whether we've already emitted the deprecation warning for
# render_mobile_toggle() in this session, to avoid log spam on every rerun.
_DEPRECATION_LOGGED_KEY = "_cdt_mobile_toggle_deprecation_logged"

MOBILE_BREAKPOINT_PX = 768


def _detect_viewport_is_mobile() -> bool:
    """Best-effort server-side viewport probe.

    Relies on ``st.context.viewport.width``, exposed by Streamlit ≥1.32.
    Returns False (desktop) on older runtimes or when the attribute is absent
    so the user can still pick "Telepon" via render_viewport_override().
    """
    try:
        ctx = getattr(st, "context", None)
        if ctx is None:
            return False
        viewport = getattr(ctx, "viewport", None)
        if viewport is None:
            return False
        width = getattr(viewport, "width", None)
        if width is None:
            return False
        return int(width) < MOBILE_BREAKPOINT_PX
    except Exception:  # pragma: no cover - defensive against runtime API drift
        return False


def is_mobile() -> bool:
    """Return True when the current request should render the mobile layout.

    Resolution order (first wins):
      1. Explicit user override (``cdt_viewport_pref`` is "mobile" or "desktop").
      2. Legacy ``mobile_mode`` flag set to True.
      3. Auto-detection via ``st.context.viewport.width`` (<768 px).
      4. Default desktop.
    """
    pref = st.session_state.get(_VIEWPORT_PREF_KEY)
    if pref == "mobile":
        return True
    if pref == "desktop":
        return False

    if st.session_state.get(_MOBILE_FLAG) is True:
        return True

    return _detect_viewport_is_mobile()


_OVERRIDE_LABELS = {
    "auto": "Otomatis",
    "mobile": "Telepon",
    "desktop": "Desktop",
}


def render_viewport_override() -> None:
    """Render the 'Tampilan' override inside an expander.

    Persists the selection in ``st.session_state[_VIEWPORT_PREF_KEY]``. Default
    is "auto", which delegates to ``st.context.viewport`` auto-detection.
    """
    if _VIEWPORT_PREF_KEY not in st.session_state:
        st.session_state[_VIEWPORT_PREF_KEY] = "auto"

    with st.expander("Pengaturan tampilan", expanded=False):
        st.radio(
            "Tampilan",
            options=["auto", "mobile", "desktop"],
            format_func=lambda v: _OVERRIDE_LABELS[v],
            horizontal=True,
            key=_VIEWPORT_PREF_KEY,
            help=(
                "Otomatis menyesuaikan dengan ukuran layar. Pilih 'Telepon' "
                "atau 'Desktop' untuk memaksa tata letak tertentu."
            ),
        )


def render_mobile_toggle() -> None:
    """Deprecated. Calls :func:`render_viewport_override` for back-compat."""
    if not st.session_state.get(_DEPRECATION_LOGGED_KEY):
        logger.warning(
            "render_mobile_toggle() is deprecated; use render_viewport_override()."
        )
        st.session_state[_DEPRECATION_LOGGED_KEY] = True
    render_viewport_override()


def responsive_tabs(labels: list[str]):
    """Return tab-like context managers: st.tabs on desktop, expanders on mobile.

    On desktop returns ``st.tabs(labels)`` directly (a Streamlit TabList).
    On mobile returns a list of ``st.expander(label, expanded=...)`` contexts —
    the first expander is open by default; the rest are collapsed.

    All elements support the ``with tabs[i]:`` pattern in both modes.

    Args:
        labels: Ordered list of tab/expander labels.

    Returns:
        A list of context managers of length ``len(labels)``.
    """
    if not is_mobile():
        return st.tabs(labels)
    return [
        st.expander(label, expanded=(i == 0))
        for i, label in enumerate(labels)
    ]


def responsive_columns(
    spec_desktop: Union[int, Sequence[float]],
    n_mobile: int = 1,
):
    """``st.columns(spec_desktop)`` on desktop; stacked rows on mobile.

    Args:
      spec_desktop: int (equal-width columns) or list of width weights.
        Passed through to st.columns on desktop.
      n_mobile: columns per row on mobile. Default 1 stacks everything.
        Must be >= 1.

    Returns:
      A list of column-like Streamlit contexts of length equal to the
      desktop column count. Usable both via tuple unpacking
      (``a, b, c = responsive_columns(3)``) and via ``with col:`` blocks.
    """
    if n_mobile < 1:
        raise ValueError("n_mobile must be >= 1")

    n_total = spec_desktop if isinstance(spec_desktop, int) else len(spec_desktop)

    if not is_mobile():
        return list(st.columns(spec_desktop))

    if n_mobile == 1:
        return [st.container() for _ in range(n_total)]

    cells: list = []
    remaining = n_total
    while remaining > 0:
        row_n = min(n_mobile, remaining)
        cells.extend(st.columns(row_n))
        remaining -= row_n
    return cells
