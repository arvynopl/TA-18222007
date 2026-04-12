# CDT Bias Detection System — UI/UX Fix Implementation Prompt

## Identity & Constraints

This is a Streamlit-based Cognitive Digital Twin (CDT) system for detecting behavioral biases in retail investors. It is a thesis project (TA-18222007, ITB). Before starting, read and strictly follow `CLAUDE.md` in this repo root. These constraints are absolute:

- **Do NOT** change any bias formula, threshold, CDT update logic, or DB schema.
- **Do NOT** add new pages, modules, or files unless explicitly instructed below.
- **Do NOT** break test suite — run `pytest tests/ -v` before and after all changes; it must stay at 85 passed, 0 failed.
- **Do NOT** use `datetime.utcnow()`, `print()`, or hold DB sessions across reruns.
- All user-facing strings must remain in **Bahasa Indonesia**.
- Touch only the files listed per fix. No other files.

---

## Fix 1 — Force Dark Theme via Streamlit Config

**File:** `.streamlit/config.toml` (create if absent)

**Problem:** `ui_helpers.py` hardcodes `background: #0D1117` on the sidebar via CSS injection, causing black sidebar + black text in light mode.

**Solution:** Enforce dark mode at the framework level so the CSS assumption is always valid. Create or update `.streamlit/config.toml`:

```toml
[theme]
base = "dark"
primaryColor = "#4A90E2"
backgroundColor = "#0D1117"
secondaryBackgroundColor = "#161B22"
textColor = "#E0E0E0"
font = "sans serif"
```

After creating this file, verify the app renders correctly in dark mode. Do not modify the CSS in `ui_helpers.py`.

---

## Fix 2 — Round 1 Candlestick Invisible Bug

**File:** `modules/simulation/ui.py`

**Problem:** `_build_full_chart()` slices `window_data[:current_round]`. At round 1, this produces a single-element list. Plotly `go.Candlestick` with one data point renders as a near-invisible thin line — the pre-window line chart visually dominates and the candlestick appears missing.

**Solution:** In `_build_full_chart()`, change the visible slice to always include at least 2 data points when `current_round == 1`, but only if the window has at least 2 rows. Also suppress the "Mulai Trading" start marker annotation on round 1 since there's no meaningful boundary to mark when only 1 real bar exists.

Locate this block in `_build_full_chart`:
```python
# --- Trading window up to current_round (candlestick) ---
visible = window_data[:current_round]
```

Replace with:
```python
# --- Trading window up to current_round (candlestick) ---
# Show at least 2 bars on round 1 to avoid single-bar Plotly rendering artifact.
display_count = max(current_round, 2) if len(window_data) >= 2 else current_round
visible = window_data[:display_count]
```

Then locate the `fig.add_annotation(... text="Mulai Trading" ...)` block. Wrap the entire `fig.add_shape(...)` + `fig.add_annotation(...)` block with a guard so it only renders when `current_round > 1`:

```python
if current_round > 1:
    fig.add_shape(
        type="line",
        x0=win_dates[0], x1=win_dates[0],
        ...
    )
    fig.add_annotation(
        x=win_dates[0],
        ...
        text="Mulai Trading",
        ...
    )
```

**Note:** The `current_round` parameter must be threaded through — the function already receives it, so no signature change is needed.

---

## Fix 3 — Move Price Indicators Above Chart

**File:** `modules/simulation/ui.py`

**Problem:** Technical indicators (price, MA5, MA20, RSI/Trend) are rendered BELOW the chart, making users look at indicators AFTER the chart has already shaped their perception.

**Solution:** In `render_simulation_page()`, inside the `with col_right:` block, move the indicators block to appear **immediately after** the stock header line and **before** `st.plotly_chart(...)`.

Current order:
1. Stock header (`st.markdown(f"**{ticker}**...")`)
2. `fig = _build_full_chart(...)`
3. `st.plotly_chart(fig, ...)`
4. Technical indicators row (`ind_cols = st.columns(4)`)
5. `st.divider()`

New order:
1. Stock header (`st.markdown(f"**{ticker}**...")`)
2. Technical indicators row (`ind_cols = st.columns(4)`)
3. `st.divider()` ← the one that was after indicators
4. `fig = _build_full_chart(...)`
5. `st.plotly_chart(fig, ...)`
6. *(remove the old divider that was between chart and order panel — replace with the one now above chart)*

Keep all variable assignments (`ma5`, `ma20`, `trend`, `rsi`, `daily_ret`, `ret_str`) in place — just move the rendering block upward.

---

## Fix 4 — MA5, MA20, RSI Contextual Tooltips

**File:** `modules/simulation/ui.py`

**Problem:** `ind_cols[1].caption(f"MA5: ...")` and `ind_cols[2].caption(f"MA20: ...")` and `ind_cols[3].caption(f"Tren: {trend} | RSI: {rsi_str}")` give raw values with no interpretive guidance for non-expert users.

**Solution:** Replace the four indicator columns with `st.metric()` calls that include `help=` parameter tooltips. The `help=` tooltip renders as a `?` icon the user can hover. Keep the display values identical; only add explanatory `help=` text.

Replace the entire `ind_cols` block:

```python
ind_cols = st.columns(4)
ind_cols[0].metric("Harga", _format_rupiah(snap["close"]), delta=ret_str)
ind_cols[1].caption(f"MA5: {_format_rupiah(ma5) if ma5 else '—'}")
ind_cols[2].caption(f"MA20: {_format_rupiah(ma20) if ma20 else '—'}")
rsi_str = f"{rsi:.0f}" if rsi is not None else "—"
ind_cols[3].caption(f"Tren: {trend.capitalize()} | RSI: {rsi_str}")
```

With:

```python
ind_cols = st.columns(4)
ind_cols[0].metric(
    "Harga Penutupan",
    _format_rupiah(snap["close"]),
    delta=ret_str,
    help="Harga penutupan hari ini. Delta menunjukkan perubahan dari hari sebelumnya.",
)
ind_cols[1].metric(
    "MA5",
    _format_rupiah(ma5) if ma5 else "—",
    help=(
        "Moving Average 5 Hari: rata-rata harga penutupan 5 hari terakhir. "
        "Jika harga saat ini di ATAS MA5, momentum jangka pendek cenderung positif. "
        "Jika di BAWAH MA5, momentum melemah."
    ),
)
ind_cols[2].metric(
    "MA20",
    _format_rupiah(ma20) if ma20 else "—",
    help=(
        "Moving Average 20 Hari: tren jangka menengah. "
        "Persilangan MA5 memotong ke atas MA20 (golden cross) sering dilihat sebagai sinyal beli. "
        "MA5 memotong ke bawah MA20 (death cross) sering dilihat sebagai sinyal jual."
    ),
)
rsi_str = f"{rsi:.0f}" if rsi is not None else "—"
ind_cols[3].metric(
    "RSI-14",
    rsi_str,
    delta=trend.capitalize() if trend and trend != "—" else None,
    delta_color="off",
    help=(
        "Relative Strength Index (14 hari): mengukur kecepatan dan besar perubahan harga. "
        "RSI > 70: kondisi overbought — harga mungkin terlalu tinggi dan bisa koreksi. "
        "RSI < 30: kondisi oversold — harga mungkin terlalu rendah dan bisa rebound. "
        "RSI 30–70: zona netral."
    ),
)
```

---

## Fix 5 — Normalize Metric Card Heights (Portfolio Strip)

**File:** `modules/simulation/ui.py`

**Problem:** In the portfolio summary strip, `c_val` has `delta=f"{delta_pct:+.1f}%"` while `c_rpnl` and `c_upnl` have no `delta`, causing unequal card heights.

**Solution:** Add `delta` with `delta_color="off"` to `c_cash`, `c_rpnl`, and `c_upnl` so all four cards render at identical height. Use a non-breaking space string `" "` as delta when no meaningful delta exists — this forces equal height without misleading the user.

Locate and replace:
```python
c_cash.metric("Kas Tersedia", _format_rupiah(portfolio.cash))
c_rpnl.metric(
    "Realized P&L",
    _format_rupiah(realized_pnl),
    delta_color="normal",
)
c_upnl.metric(
    "Unrealized P&L",
    _format_rupiah(unrealized_pnl),
    delta_color="normal",
)
```

With:
```python
c_cash.metric(
    "Kas Tersedia",
    _format_rupiah(portfolio.cash),
    delta=f"{portfolio.cash - INITIAL_CAPITAL:+,.0f}" if portfolio.cash != INITIAL_CAPITAL else " ",
    delta_color="off",
)
c_rpnl.metric(
    "Realized P&L",
    _format_rupiah(realized_pnl),
    delta=f"{realized_pnl:+,.0f}" if realized_pnl != 0 else " ",
    delta_color="normal",
)
c_upnl.metric(
    "Unrealized P&L",
    _format_rupiah(unrealized_pnl),
    delta=f"{unrealized_pnl:+,.0f}" if unrealized_pnl != 0 else " ",
    delta_color="normal",
)
```

**File:** `app.py`

**Problem:** In `_page_profil()`, `c1` has no delta, `c2` has a percentage string, `c3` has `delta=f"Skor: {rp:.2f}"` — three different shapes causing height mismatch.

Locate and replace:
```python
c1.metric("Total Sesi", profile_data["session_count"])
c2.metric(
    "Stabilitas",
    f"{si:.0%}",
    help="Seberapa konsisten pola biasmu antar sesi (100% = sangat konsisten)",
)
c3.metric("Preferensi Risiko", rp_label, delta=f"Skor: {rp:.2f}", delta_color="off")
```

With:
```python
c1.metric(
    "Total Sesi",
    profile_data["session_count"],
    delta=" ",
    delta_color="off",
)
c2.metric(
    "Stabilitas",
    f"{si:.0%}",
    delta=" ",
    delta_color="off",
    help="Seberapa konsisten pola biasmu antar sesi (100% = sangat konsisten)",
)
c3.metric(
    "Preferensi Risiko",
    rp_label,
    delta=f"Skor: {rp:.2f}",
    delta_color="off",
    help="Dihitung dari volatilitas saham yang kamu pilih, diperbarui tiap sesi dengan EMA.",
)
```

---

## Fix 6 — Experience Level Definitions at Registration

**File:** `app.py`

**Problem:** The `st.selectbox` for `experience_level` in `_page_beranda()` shows "Pemula / Menengah / Berpengalaman" with no definition. UAT participants won't know how to self-classify.

**Solution:** Add a `st.caption()` immediately below the selectbox widget (before `submitted = st.form_submit_button(...)`):

```python
st.caption(
    "**Pemula:** Belum pernah atau jarang berinvestasi saham. "
    "**Menengah:** Sudah aktif berinvestasi 1–3 tahun. "
    "**Berpengalaman:** Investor aktif >3 tahun atau memiliki latar belakang keuangan formal."
)
```

Place this inside the `with st.form("login_form"):` block, after the `experience` selectbox and before the `submitted` form submit button.

---

## Fix 7 — Insight Section: Add Actionable CTA

**File:** `app.py`

**Problem:** In `_page_profil()`, the insight section ends with a status message (st.success/st.info/st.warning) and caption, but gives no next step. Users are stranded after reading their bias status.

**Solution:** After the `if profile_data["last_updated_at"]:` caption block and before the data export divider, add a navigation button:

```python
st.divider()
col_cta1, col_cta2 = st.columns(2)
with col_cta1:
    if st.button("📋 Lihat Umpan Balik Terakhir →", use_container_width=True):
        st.session_state["current_page"] = "Hasil Analisis & Umpan Balik"
        st.rerun()
with col_cta2:
    if st.button("🚀 Mulai Sesi Baru →", use_container_width=True, type="primary"):
        st.session_state["current_page"] = "Simulasi Investasi"
        st.rerun()
```

Place this block **after** the `st.caption(f"Terakhir diperbarui: ...")` line and **before** the `st.divider()` that precedes "Ekspor Data".

---

## Fix 8 — Gauge Threshold Annotations on Feedback Page

**File:** `modules/feedback/renderer.py`

**Problem:** The three bias gauge charts show raw scores with no scale legend. A user seeing OCS = 0.47 on a 0–1 gauge has no idea whether that is mild, moderate, or severe.

**Solution:** After each `st.plotly_chart(fig, ...)` call inside the `g1`, `g2`, `g3` columns in `render_feedback_page()`, add a `st.caption()` sourced from `config.py` constants (already imported at the top of the file):

Replace the gauge rendering block:
```python
g1, g2, g3 = st.columns(3)
with g1:
    sev = classify_severity(metric_data["ocs"], OCS_SEVERE, OCS_MODERATE, OCS_MILD)
    fig = build_severity_gauge(metric_data["ocs"], 1.0, "Overconfidence", sev)
    st.plotly_chart(fig, use_container_width=True)
with g2:
    sev = classify_severity(metric_data["dei"], DEI_SEVERE, DEI_MODERATE, DEI_MILD)
    fig = build_severity_gauge(metric_data["dei"], 1.0, "Efek Disposisi", sev)
    st.plotly_chart(fig, use_container_width=True)
with g3:
    sev = classify_severity(metric_data["lai"], LAI_SEVERE, LAI_MODERATE, LAI_SEVERE)
    fig = build_severity_gauge(metric_data["lai"], 3.0, "Loss Aversion", sev)
    st.plotly_chart(fig, use_container_width=True)
```

With:
```python
g1, g2, g3 = st.columns(3)
with g1:
    sev = classify_severity(metric_data["ocs"], OCS_SEVERE, OCS_MODERATE, OCS_MILD)
    fig = build_severity_gauge(metric_data["ocs"], 1.0, "Overconfidence", sev)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Ambang batas — Ringan: >{OCS_MILD} | Sedang: >{OCS_MODERATE} | Berat: >{OCS_SEVERE}"
    )
with g2:
    sev = classify_severity(metric_data["dei"], DEI_SEVERE, DEI_MODERATE, DEI_MILD)
    fig = build_severity_gauge(metric_data["dei"], 1.0, "Efek Disposisi", sev)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Ambang batas — Ringan: >{DEI_MILD} | Sedang: >{DEI_MODERATE} | Berat: >{DEI_SEVERE}"
    )
with g3:
    sev = classify_severity(metric_data["lai"], LAI_SEVERE, LAI_MODERATE, LAI_MILD)
    fig = build_severity_gauge(metric_data["lai"], 3.0, "Loss Aversion", sev)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Ambang batas — Ringan: >{LAI_MILD}× | Sedang: >{LAI_MODERATE}× | Berat: >{LAI_SEVERE}×  "
        f"(rasio durasi tahan rugi vs. untung)"
    )
```

**Note:** Verify the import at the top of `renderer.py` already includes `LAI_MILD` — it currently imports `LAI_SEVERE, LAI_MODERATE, LAI_MILD` via the existing block, so no import changes needed.

---

## Fix 9 — Rename "Konfirmasi" Button and Clarify Two-Step Flow

**File:** `modules/simulation/ui.py`

**Problem:** Users may confuse "Konfirmasi Beli BBCA" (adds to queue) with actual trade execution. The two-step flow (queue → execute all) is not visually distinguished.

**Solution A — Button label:** Change the form submit button label from:
```python
order_submitted = st.form_submit_button(
    f"Konfirmasi {action_type} {ticker}",
    use_container_width=True,
)
```
To:
```python
order_submitted = st.form_submit_button(
    f"➕ Tambahkan ke Antrean: {action_type} {ticker}",
    use_container_width=True,
)
```

**Solution B — Guide copy:** In the `with st.expander("Panduan Simulasi", ...)` block, replace the instruction line:
```
- Klik **Konfirmasi** untuk menyimpan keputusan, lalu klik **Eksekusi Semua** untuk mengonfirmasi semua keputusan dan lanjut ke putaran berikutnya
```
With:
```
- Klik **Tambahkan ke Antrean** untuk mencatat keputusan satu saham — ini belum mengeksekusi transaksi
- Setelah selesai memilih semua saham, klik **Eksekusi Semua** di bagian bawah untuk mengeksekusi semua antrean dan lanjut ke putaran berikutnya
```

---

## Fix 10 — Risk Preference: Introduce at Journey Start

**File:** `app.py`

**Problem:** Risk preference is a CDT output metric but is invisible until the user reaches Profil Kognitif (4th page). First-time users complete 14 rounds not knowing this metric is being tracked.

**Solution:** In `_page_beranda()`, inside the `with st.expander("ℹ️ Bagaimana sistem ini bekerja?", ...)` block, extend the existing step 3 bullet in the markdown to reference risk preference:

Find this string in the markdown:
```
3. **Profil Kognitif** — Profilmu diperbarui setelah setiap sesi menggunakan
   model *Cognitive Digital Twin* (CDT) berbasis EMA.
```

Replace with:
```
3. **Profil Kognitif** — Profilmu diperbarui setelah setiap sesi menggunakan
   model *Cognitive Digital Twin* (CDT) berbasis EMA. Sistem juga mendeteksi
   **Preferensi Risiko** kamu (Konservatif / Moderat / Agresif) berdasarkan
   volatilitas saham yang kamu pilih — tanpa kamu harus mengisi kuesioner.
```

---

## Verification Steps

After all changes are applied, run these checks in order:

```bash
# 1. Tests must still pass (85 passed, 0 failed)
pytest tests/ -v

# 2. Verify config.toml is syntactically valid
python -c "import tomllib; tomllib.load(open('.streamlit/config.toml', 'rb'))"

# 3. Smoke test the app renders without import errors
python -c "import app"

# 4. Run the app and manually verify:
streamlit run app.py
```

**Manual UAT checklist (smoke test each fix):**
- [ ] App launches in dark mode; no light/dark sidebar inconsistency
- [ ] Round 1 shows at least 2 candlestick bars; "Mulai Trading" marker absent on round 1 only
- [ ] Price/MA5/MA20/RSI indicators appear ABOVE the chart with `?` tooltip icons
- [ ] All 4 portfolio metric cards (Nilai/Kas/R-P&L/U-P&L) have equal height
- [ ] All 3 profile metric cards (Total Sesi/Stabilitas/Preferensi Risiko) have equal height
- [ ] Registration form shows one-line experience level descriptions
- [ ] Profil Kognitif insight section shows two CTA buttons at bottom
- [ ] Feedback page gauge charts show threshold caption below each gauge
- [ ] Order button reads "Tambahkan ke Antrean: Beli [TICKER]"
- [ ] "Bagaimana sistem ini bekerja?" expander mentions Preferensi Risiko in step 3
