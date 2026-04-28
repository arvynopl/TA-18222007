# Mobile Audit Notes — Phase 2 input for Phase 3

**Status:** Static audit only. Phase 2 introduced no UI changes; this
document captures observed mobile-layout risks for Phase 3 to fix.

**Method:** Source inspection of every `st.columns()`, `st.plotly_chart()`,
`st.dataframe()`, and `st.table()` call site, cross-referenced with the
existing `render_mobile_banner()` warning that already advises users to
prefer ≥10-inch screens.

> **Note on browser emulation:** the working environment for this phase
> does not have Streamlit or a browser available, so the iPhone 14 / Pixel 7
> screenshots called for in the prompt could not be captured in-session.
> Phase 3 must reproduce these viewports (375 / 390 / 412 / 768 / 1440 px)
> in Chrome DevTools and replace the "static finding" rows below with
> concrete before/after evidence.

---

## Target viewport widths (for Phase 3 verification)

| Device          | Width  |
| --------------- | ------ |
| iPhone SE       | 375 px |
| iPhone 14       | 390 px |
| Pixel 7         | 412 px |
| iPad Mini       | 768 px |
| Desktop (1080p) | 1440 px |

---

## Findings

Each finding lists: **file:line** → pattern → expected mobile breakage.
None of these are fixed in Phase 2.

### F1 — Candlestick chart height & responsiveness

- `modules/simulation/ui.py:251` — `apply_chart_theme(fig, height=420)`
- The candlestick + volume subplot is fixed at 420 px tall regardless of
  viewport. On a 390 px-wide phone, the chart compresses horizontally
  while keeping full height, producing illegible candles.
- **Phase 3 action:** add a viewport-aware height (e.g. 280 px on phone,
  420 px on desktop) and add an `st.toggle("Tampilan ringkas untuk
  mobile")` that swaps the candlestick for a single-line close trace.
  Preserve bias-relevant signal: trajectory shape, MA5/MA20 overlays,
  volume bar magnitude.
- Note: `use_container_width=True` is already set at the call site
  (`modules/simulation/ui.py:907`), so width responsiveness is fine —
  only height and primitive choice need work.

### F2 — High-arity column rows that break below ~600 px

Streamlit's `st.columns(N)` does not collapse on narrow viewports; all
N columns stay side-by-side and each becomes ~ `viewport / N` wide. On
a 390 px phone with `N >= 3` each column is < 130 px and content
truncates or wraps badly.

| File:line                                       | N | Mitigation needed                                |
| ----------------------------------------------- | - | ------------------------------------------------ |
| `app.py:626` `c1, c2, c3 = st.columns(3)`       | 3 | Replace with `responsive_columns(3, mobile=1)`. |
| `modules/feedback/renderer.py:213` `st.columns(min(n_sessions, 8))` | up to 8 | Worst offender. Wrap each session into 2 rows of 4 on tablet, single column on phone. |
| `modules/feedback/renderer.py:505` `cols_corr = st.columns(3)` | 3 | Drop to 1 col on phone. |
| `modules/feedback/renderer.py:632` `col_a, col_b, col_c = st.columns(3)` | 3 | Drop to 1 col on phone. |
| `modules/feedback/renderer.py:907` `c1, c2, c3, c4 = st.columns(4)` | 4 | Drop to 2 cols on tablet, 1 on phone. |
| `modules/feedback/renderer.py:959` `pill_cols = st.columns(3)` | 3 | Drop to 1 col on phone. |
| `modules/feedback/renderer.py:1030` `g1, g2, g3 = st.columns(3)` | 3 | Drop to 1 col on phone. |
| `modules/feedback/renderer.py:1152` `h1, h2, h3, h4 = st.columns([2,1.5,1.5,2])` | 4 | History table header row. Stack as cards on phone. |
| `modules/feedback/renderer.py:1161` (loop body) | 4 | Same as above — paired with the header. |
| `modules/simulation/ui.py:619` `c1, c2, c3 = st.columns(3)` | 3 | Drop to 1 col on phone. |
| `modules/simulation/ui.py:667` `c_val, c_cash, c_rpnl, c_upnl = st.columns(4)` | 4 | KPI strip. Drop to 2x2 on tablet, 1x4 on phone. |
| `modules/simulation/ui.py:864` `ind_cols = st.columns(4)` | 4 | Drop to 2x2 on tablet, 1 col on phone. |
| `modules/utils/ui_helpers.py:117` `cols = st.columns(len(NAV_ITEMS))` | 4 | Top nav. Already protected by the existing mobile banner that asks users to prefer larger screens, but should be made tab-bar-style on phone. |

Two-column layouts (`st.columns(2)` and `st.columns([a, b])`) generally
remain usable on phone because each column is ~ 195 px wide. They are
acceptable as-is unless the cell content itself overflows.

### F3 — DataFrames (only one true data table)

- `modules/feedback/renderer.py:206` is `st.table(rows)`. `st.table` is
  not horizontally scrollable on Streamlit; wide content truncates.
  Phase 3 must check the row width — if `len(rows[0]) > 5`, switch to
  `st.dataframe(rows, use_container_width=True)` or hide low-priority
  columns on phone.
- No `st.dataframe()` calls were found in the codebase, so the DataFrame
  audit reduces to F3 alone for now. If new tables are added in Phase 3
  they must default to `use_container_width=True`.

### F4 — Feedback page long-form Bahasa Indonesia text blocks

- `modules/feedback/renderer.py` — most cells render long copy via
  `st.markdown` inside columns. No fixed-width wrappers were found, so
  text reflow itself is fine. The risk is that the *column width* (see
  F2) shrinks the text into very narrow runs, producing >30 lines of
  one-or-two-word breaks on phone.
- **Phase 3 action:** stacked single-column layout on phone fixes both
  F2 and F4 simultaneously. No font-size changes needed if columns drop
  to 1 — verify in DevTools at 390 px.

### F5 — Already-correct primitives (no Phase 3 work expected)

The following are already mobile-friendly and require no change:

- `use_container_width=True` is set on every `st.plotly_chart()` and
  every primary action button (`app.py:251`, `app.py:324`, etc.).
- `render_mobile_banner()` (`modules/utils/ui_helpers.py:133`) already
  shows a yellow advisory below 768 px; keep it as a soft fallback.
- The existing CSS in `inject_custom_css()` is responsive-friendly (no
  hardcoded `min-width` that would break the viewport).

---

## Phase 3 entry checklist

Before starting Phase 3:

1. [ ] Reproduce each finding above in Chrome DevTools at 390 px and
       capture a "before" screenshot.
2. [ ] Build the `modules/utils/layout.py:responsive_columns()` helper
       referenced by the Phase 3 prompt and migrate the F2 call sites
       in priority order: simulation → feedback → app.
3. [ ] Add the `st.toggle("Tampilan ringkas untuk mobile")` candlestick
       fallback for F1.
4. [ ] Re-shoot screenshots at the five target widths and append a
       "Phase 3 — after" section to this file.
5. [ ] Run `pytest tests/ -v` — must remain 85+ passed, 0 failed.

---

## Remaining gaps (filled in by Phase 3)

_To be populated during Phase 3 with any breakage that survives the
fixes above (e.g. third-party Plotly toolbar overflow, Streamlit native
sidebar edge cases on iOS Safari, etc.)._
