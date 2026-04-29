# Mobile Audit Notes — Phase 3 fixes applied

**Status:** Phase 3 fixes implemented. Phase 2 captured the static
findings; this file now records the before/after for each.

**Method recap:** every `st.columns()`, `st.plotly_chart()`,
`st.dataframe()`, `st.table()` call site was reviewed against five
target viewports (375 / 390 / 412 / 768 / 1440 px). Mobile mode is
opted-in via the global `Mode mobile` toggle rendered by
`modules.utils.layout.render_mobile_toggle()` in the page header.

> **Browser-emulation caveat:** the working environment for this phase
> still does not have a GUI / Chrome DevTools available, so the
> screenshots called for in the Phase 3 prompt are described
> textually rather than captured as PNGs. Layout was verified by
> static inspection plus a runtime check of `_build_full_chart` /
> `_build_compact_line_chart` returning the expected trace counts and
> heights (8 traces / 420 px desktop vs 2 traces / 280 px compact).
> When the live URL is up, repeat the visual smoke test in DevTools.

---

## Target viewport widths

| Device          | Width  | Status after Phase 3 (textual description)                                  |
| --------------- | ------ | ---------------------------------------------------------------------------- |
| iPhone SE       | 375 px | Acceptable when *Mode mobile* is on: nav stacks 2x2, KPI strips 2x2, candlestick → line. |
| iPhone 14       | 390 px | Same as above. *Mode mobile* drives single-col / 2x2 layouts depending on N. |
| Pixel 7         | 412 px | Same as iPhone 14. Slightly more breathing room on 2-col rows.              |
| iPad Mini       | 768 px | Above the breakpoint — desktop layout is fine; *Mode mobile* still works if user opts in. |
| Desktop (1080p) | 1440 px | Unchanged from pre-Phase 3 desktop layout.                                  |

---

## Findings — Phase 3 resolution

### F1 — Candlestick chart height & responsiveness

**Before:** `modules/simulation/ui.py:_build_full_chart` was always a
candlestick + volume subplot at fixed 420 px. On a 390 px viewport the
14 candle bars compress to ~10 px each — illegible — while the chart
keeps full vertical real estate.

**After:**

- `_build_full_chart` now accepts `compact: bool = False`. On `compact=True`
  it delegates to a new `_build_compact_line_chart` that renders the
  closing-price trajectory as a single line at 280 px height. Pre-window
  history is shown as a muted grey line; the trading window is colored
  green/red depending on net direction; the "Mulai Trading" boundary
  marker is preserved so the bias-relevant signal (when did the user
  start trading) is intact.
- A per-chart `st.toggle("Tampilan ringkas untuk mobile")` is rendered
  immediately above the chart (`modules/simulation/ui.py:~999`). Default
  state matches the global *Mode mobile* flag; the user can override it
  per chart.
- `use_container_width=True` was already set at the call site.

**Verification:**
```
fig_full.layout.height == 420  (candlestick + volume, 8 traces)
fig_compact.layout.height == 280  (line only, 2 traces)
```

### F2 — High-arity column rows

**Before:** thirteen `st.columns(N>=3)` call sites; on a 390 px phone
each column is `< 130 px`, so labels and metric values either wrap
awkwardly or clip.

**After:** every site migrated to `responsive_columns(spec_desktop, n_mobile=…)`
from `modules.utils.layout`. Behaviour:

- On desktop (Mode mobile off) the helper passes through to `st.columns`
  unchanged — no regression.
- On mobile (Mode mobile on), `n_mobile` controls how cells stack:
  `n_mobile=1` → full-width rows; `n_mobile=2` → 2-up grid (used for
  KPI strips that benefit from horizontal pairing).

| File:line                                         | Before        | After (`responsive_columns`) | Mobile shape |
| ------------------------------------------------- | ------------- | ---------------------------- | ------------ |
| `app.py:628`                                      | `st.columns(3)` | `responsive_columns(3)`       | 1×3          |
| `modules/feedback/renderer.py:213`                | `st.columns(min(n_sessions, 8))` | `responsive_columns(min(n_sessions, 8), n_mobile=4)` | rows of 4   |
| `modules/feedback/renderer.py:505`                | `st.columns(3)` | `responsive_columns(3)`       | 1×3          |
| `modules/feedback/renderer.py:632`                | `st.columns(3)` | `responsive_columns(3)`       | 1×3          |
| `modules/feedback/renderer.py:907`                | `st.columns(4)` | `responsive_columns(4, n_mobile=2)` | 2×2     |
| `modules/feedback/renderer.py:959`                | `st.columns(3)` | `responsive_columns(3)`       | 1×3          |
| `modules/feedback/renderer.py:1030`               | `st.columns(3)` | `responsive_columns(3)`       | 1×3          |
| `modules/feedback/renderer.py:1152` (header row)  | `st.columns([2,1.5,1.5,2])` | gated by `is_mobile()` — header is hidden on mobile, labels are inlined into each body row | n/a (suppressed) |
| `modules/feedback/renderer.py:1161` (body row)    | `st.columns([2,1.5,1.5,2])` | `responsive_columns([2,1.5,1.5,2])` + inlined labels on mobile | 1×4 stacked  |
| `modules/simulation/ui.py:620`                    | `st.columns(3)` | `responsive_columns(3)`       | 1×3          |
| `modules/simulation/ui.py:668`                    | `st.columns(4)` | `responsive_columns(4, n_mobile=2)` | 2×2     |
| `modules/simulation/ui.py:865`                    | `st.columns(4)` | `responsive_columns(4, n_mobile=2)` | 2×2     |
| `modules/utils/ui_helpers.py:117` (top nav)       | `st.columns(4)` | `responsive_columns(4, n_mobile=2)` | 2×2     |

Two-column layouts (`st.columns(2)`, `st.columns([a, b])`) were left
alone — at 390 px each cell is ~195 px wide, which is acceptable for
form labels and button pairs.

### F3 — DataFrames

**Before:** one `st.table(rows)` at `modules/feedback/renderer.py:207`
with 4 columns (Sesi + 3 bias names). No `st.dataframe()` calls.

**After:** verified that the table has only 4 columns (≤ the 5-col
threshold in the prompt) with short content (`💡 Ringan`-style cells),
so it fits on a 390 px viewport without truncation. No conversion to
`st.dataframe` was made because `tests/test_renderer.py:259` asserts
`mock_st.table.assert_called_once()` — switching primitives would
break that test without a UX win. Future tables added to the codebase
should default to `st.dataframe(..., use_container_width=True)` per the
Phase 3 prompt.

### F4 — Feedback page long-form Bahasa Indonesia text

**Before:** long markdown blocks rendered inside narrow columns wrapped
into one- or two-word lines on phone.

**After:** since every high-arity column row in `feedback/renderer.py`
now collapses to single-column on mobile via `responsive_columns`,
markdown blocks have the full viewport width to flow into. No font-size
changes were needed. Cross-checked `inject_custom_css()` and
`render_top_nav` for hardcoded widths:

- `modules/utils/ui_helpers.py:110` — the `min-width: 240px` on nav
  buttons would have caused horizontal overflow on phone (240 px > the
  ~195 px-per-cell budget at 390 px). Wrapped in
  `@media (min-width: 769px)` so the rule only applies above the
  tablet breakpoint.
- No other fixed widths found in `inject_custom_css()`.

### F5 — Already-correct primitives (unchanged)

- `use_container_width=True` is set on every `st.plotly_chart()` and
  every primary action button.
- `render_mobile_banner()` continues to show a yellow advisory below
  768 px — kept as a soft fallback for users who do not toggle Mode
  mobile.
- The new `render_mobile_toggle()` is rendered in `_render_header()`
  on every page (after the banner, before the top nav), so users get
  a single, persistent control to opt into mobile mode.

---

## Per-page smoke test at 390 px (textual)

All five pages rely on the same header (`_render_header` in `app.py`),
which now emits the *Mode mobile* toggle plus the existing yellow
banner. Pages tested by static read-through with the toggle ON:

1. **Beranda (Login / Registrasi).** Forms use 2-col layouts only —
   already mobile-fine. Buttons all have `use_container_width=True`.
2. **Simulasi Investasi.** KPI strip (4 cols) → 2×2 grid. Indicator
   strip (4 cols) → 2×2 grid. Candlestick → line chart at 280 px.
   Final-results 3-col strip → 1×3 stacked.
3. **Hasil Analisis & Umpan Balik.** Severity pills (3 cols) → stacked.
   Gauges (3 cols) → stacked. Per-session timeline strip (up to 8
   cols) → rows of 4. Self-vs-detected comparison: header hidden on
   mobile, each row rendered as a labeled stack of four cards.
4. **Profil Kognitif Saya.** Profile metrics (3 cols) → stacked.
5. **Survei pasca-sesi (modal).** Already a single column form.

## Remaining gaps

These are **not blockers**, but are worth tracking for Phase 4 polish:

1. **Plotly toolbar overflow on iOS Safari.** Plotly's modebar
   (zoom / reset / camera icons) sits at top-right of every chart and
   is not affected by `use_container_width`. On 375-px viewports it
   can overlap the chart title. Mitigation in Phase 4: pass
   `config={"displayModeBar": False}` to `st.plotly_chart` for the
   compact path (the user does not need pan/zoom on a tiny chart).
2. **Toggle persistence across reruns.** `st.toggle` with `key=` is
   persisted in `st.session_state` for that browser session, but does
   not survive a hard reload (cookieless). Acceptable for UAT.
3. **The candlestick toggle re-creates per stock_id.** Each chart has
   its own `chart_compact_<sid>` key. Switching stock resets the user's
   preference. Could centralise via the global *Mode mobile* flag —
   left as-is per the Phase 3 prompt's explicit per-chart toggle.
4. **`render_top_nav` button rebinding when going from 2×2 to 1×4.**
   Streamlit's button identity is keyed by the `key=` arg
   (`cdt_nav_<label>`), so switching `Mode mobile` mid-session does
   not reset state — but the rendered card layout reflows. No fix
   needed.
5. **No JS-injected viewport detection.** As predicted in the Phase 3
   prompt, neither session_state nor injected JS gives us a reliable
   server-side viewport width. Falling back to the user-facing toggle
   per the prompt's stated guidance.

---

## Phase 3 verification

- `python3 -m pytest tests/ -q` → **275 passed, 4 skipped** (Postgres-compat,
  expected when `CDT_DATABASE_URL` is unset). Same green count as Phase 2.
- `streamlit run app.py` → boots cleanly, no warnings.
- `_build_full_chart` smoke-checked end-to-end:
  - desktop path: 8 traces at 420 px;
  - compact path: 2 traces at 280 px.
