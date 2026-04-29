"""
modules/utils/layout.py — Mobile-aware layout helpers for the CDT app.

Streamlit cannot reliably read viewport width from the server side, so we
expose a session_state flag (`mobile_mode`) that the user toggles via
`render_mobile_toggle()` at the top of every page. Layouts call
`responsive_columns(...)` instead of `st.columns(...)` so high-arity column
rows that break on phones (N >= 3 → cells < 130 px on a 390 px viewport)
collapse into a stacked single column on mobile.
"""
from __future__ import annotations

from typing import Sequence, Union

import streamlit as st


_MOBILE_FLAG = "mobile_mode"


def is_mobile() -> bool:
    return bool(st.session_state.get(_MOBILE_FLAG, False))


def render_mobile_toggle() -> None:
    """Render the user-facing 'Mode mobile' toggle.

    Bound to st.session_state["mobile_mode"]. Render once per page.
    """
    st.toggle(
        "Mode mobile",
        key=_MOBILE_FLAG,
        help=(
            "Aktifkan agar tata letak menyesuaikan layar telepon: "
            "kolom dirapikan menjadi satu, grafik harga lebih ringkas."
        ),
    )


def responsive_columns(
    spec_desktop: Union[int, Sequence[float]],
    n_mobile: int = 1,
):
    """`st.columns(spec_desktop)` on desktop; stacked rows on mobile.

    Args:
      spec_desktop: int (equal-width columns) or list of width weights.
        Passed through to st.columns on desktop.
      n_mobile: columns per row on mobile. Default 1 stacks everything.
        Must be >= 1.

    Returns:
      A list of column-like Streamlit contexts of length equal to the
      desktop column count. Usable both via tuple unpacking
      (`a, b, c = responsive_columns(3)`) and via `with col:` blocks.
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
