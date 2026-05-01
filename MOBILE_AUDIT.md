# Mobile audit — end-user pages (Pre-UAT)

Scope: end-user pages walked during a UAT session — Beranda / auth flow,
Simulasi Investasi, Hasil Analisis & Umpan Balik, Profil Kognitif Saya. Audit
performed at a 380×800 viewport (iPhone SE class) with the auto-detect path
shipped in A1 active.

Categories: T (tap-target), O (overflow), P (padding/spacing), L
(legend/chart), TYP (typography), N (navigation).

Severity: 🔴 blocks UAT walk · 🟠 friction · 🟢 cosmetic.

---

## Header (`app.py:_render_header`)

| # | File:line | Cat | Sev | Defect | Fix |
|---|---|---|---|---|---|
| 1 | `app.py:156` | TYP | 🟠 | `### Kenali Pola Investasi Anda` renders ~26 px on mobile and consumes ~10% of vertical fold | Add `@media (max-width: 480px)` rule in `inject_custom_css()` that scales `h1–h4` down by ~25%. |
| 2 | `app.py:154` | — | 🟢 | `responsive_columns([5, 1], n_mobile=1)` already stacks user identity correctly | none |

## Coach mark (`modules/utils/ui_helpers.py:render_coach_mark_onboarding`)

| # | File:line | Cat | Sev | Defect | Fix |
|---|---|---|---|---|---|
| 3 | `ui_helpers.py:687` (CSS) | P | 🟢 | Desktop `.cdt-coach-card` padding is `32px 36px`; mobile already overridden to `18px 16px` via `@media (max-width: 640px)` | none — already at or below the 20×18 target |
| 4 | `ui_helpers.py:723` | T | 🟠 | `_, btn_col = st.columns([2, 1])` keeps the action button at ~33% width on mobile, leaving 2/3 of the row blank | switch to `responsive_columns([2, 1], n_mobile=1)` so the button fills the row on mobile |

## Simulation page (`modules/simulation/ui.py:render_simulation_page`)

| # | File:line | Cat | Sev | Defect | Fix |
|---|---|---|---|---|---|
| 5 | `ui.py:1254` | T | 🟢 | Form submit button — covered by global CSS `.stButton > button { min-height: 48px }` at `≤640 px` | none |
| 6 | `ui.py:1287` | T | 🟢 | Execute round button — same global CSS | none |
| 7 | `ui.py:998–1012` | O | 🟢 | "Posisi Terbuka" caption strings run long (`🟢 **BBCA**: 42 lbr @ Rp 9,000  •  Kas bila ditutup: Rp 378,000  (+Rp 5,000)`) — wraps cleanly inside narrow column but each line spans 3 visual lines | none — wraps don't truncate data; promoting to `column_config` was scoped out for UAT |
| 8 | `ui.py:1190–1196` | T | 🟢 | Action radio (Beli/Jual/Tahan) horizontal — three short labels fit ~40 px each on a 380 px viewport, above 44 px target combined with padding | none |
| 9 | `ui.py:1218` & `1232` | T | 🟢 | `st.number_input` for quantity is on its own row above the submit button; tap target compliant | none |
| 10 | `ui.py:858` | — | 🟢 | Session-complete metrics use `responsive_columns(3)` | none |

## Feedback page (`modules/feedback/renderer.py:render_feedback_page`)

| # | File:line | Cat | Sev | Defect | Fix |
|---|---|---|---|---|---|
| 11 | `renderer.py:1035` | — | 🟢 | Gauges stack via `responsive_columns(3)`, A2 shrunk gauge height to 160 px | none |
| 12 | `renderer.py:1158` | — | 🟢 | Stated-vs-revealed table header skipped on mobile via `if not is_mobile()`; body inlines labels per row | none |
| 13 | `renderer.py:1096` | T | 🟠 | `col_new, col_profile = st.columns(2)` — two CTAs squeezed to 50% width on mobile = ~165 px each (under width budget for full Bahasa labels) | switch to `responsive_columns(2, n_mobile=1)` |
| 14 | `renderer.py:483–492` (heatmap) | L | — | Migrated to `apply_chart_theme(mobile_legend="hide")` in A2 | done in A2 |
| 15 | `renderer.py:675–684` (anomaly bars) | L | — | Migrated to `apply_chart_theme(mobile_legend="hide")` in A2 | done in A2 |

## Cognitive Profile page (`app.py:_page_profil`)

| # | File:line | Cat | Sev | Defect | Fix |
|---|---|---|---|---|---|
| 16 | `app.py:631` | — | 🟢 | KPI strip uses `responsive_columns(3)` | none |
| 17 | `app.py:687–693` | L | — | `build_dual_radar_chart` height + legend reflowed in A2 (440 → 360, legend `y=-0.45`) | done in A2 |
| 18 | `app.py:707–728` | L | — | "Riwayat Metrik per Sesi" line chart uses `apply_chart_theme(height=380)` — A2's mobile path drops it to 266 px and stacks the legend on top | done in A2 (no callsite change needed) |
| 19 | `app.py:759–767` | T | 🟠 | `col_cta1, col_cta2 = st.columns(2)` — same defect as #13 on the feedback page | switch to `responsive_columns(2, n_mobile=1)` |

## Auth flow (`app.py:_page_beranda` and friends)

Walked the auth flow at 380 px: Likert questions render full-width radios via
Streamlit defaults; submit button covered by `min-height: 48px` global rule.
No defect surfaced beyond what is already addressed.

---

## Patch order

1. Coach mark button row → `responsive_columns([2, 1], n_mobile=1)` (#4).
2. Profile-page CTA pair → `responsive_columns(2, n_mobile=1)` (#19).
3. Feedback-page CTA pair → `responsive_columns(2, n_mobile=1)` (#13).
4. CSS heading scale rule for `≤480 px` (#1).

All four are isolated edits with no behavior change on desktop.
