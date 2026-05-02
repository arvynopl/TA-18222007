"""
pages/researcher.py — Mode peneliti (researcher view).

Halaman tersembunyi untuk inspeksi data UAT pada level kohort. Akses melalui
URL ``/?view=researcher`` dan dilindungi kata sandi (env var
``CDT_RESEARCHER_PASSWORD``). Tidak ada tombol navigasi di header utama.

Bagian (urutan tab):
    1. Ringkasan Kohort UAT
    2. Tabel Peserta
    3. Distribusi Bias (DEI / OCS / LAI)
    4. Trajektori CDT Longitudinal
    5. Korelasi Inter-Bias
    6. Progresi Kohort per Sesi
    7. Survei vs. Hasil Observasi
    8. Survei UAT
    9. Performa Model ML
    10. Ekspor Massal CSV
"""

from __future__ import annotations

import csv
import io
import logging
import math
from collections import Counter

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config
from database.connection import get_session
from modules.utils.layout import responsive_columns, responsive_tabs
from modules.utils.research_charts import (
    bootstrap_ci,
    kde_values,
    ols_confidence_band,
    ols_fit,
    pearson_with_p,
    significance_stars,
)
from modules.utils.research_export import (
    compute_cohort_session_progression,
    export_all_sessions_csv,
    export_all_users_csv,
    export_cdt_snapshots_csv,
    export_post_session_surveys_csv,
    export_uat_feedback_csv,
    get_cohort_summary,
    load_model_performance,
)
from modules.utils.ui_helpers import (
    SEVERITY_COLORS, apply_chart_theme, fmt_datetime_wib,
    inject_custom_css, render_mobile_banner,
)

logger = logging.getLogger(__name__)

# Colour for data below the "mild" threshold (no bias zone).
_NO_BIAS_COLOR = "#d1d5db"

# Quartile line colours for the trajectory chart (Q1=blue … Q4=red).
_Q_COLORS = ["#60a5fa", "#4ade80", "#fb923c", "#f87171"]
_Q_LABELS = [
    "Kuartil 1 (terendah)",
    "Kuartil 2",
    "Kuartil 3",
    "Kuartil 4 (tertinggi)",
]

# Bias display metadata used by multiple sections.
_BIAS_META = {
    "dei": ("DEI (|DEI|)", "#3b82f6"),
    "ocs": ("OCS", "#22c55e"),
    "lai": ("LAI", "#f59e0b"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _csv_bytes(rows: list[dict]) -> bytes:
    """Serialise a list-of-dicts to CSV bytes (UTF-8) for st.download_button."""
    if not rows:
        return "".encode("utf-8")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Compute Pearson r between two equal-length numeric lists.

    Returns None when n < 2 or either series has zero variance.
    """
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(sx * sy)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert #rrggbb to rgba(r,g,b,alpha)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _mobile_scroll_top() -> None:
    """Inject a CSS-only 'Ke atas' floating action button for mobile."""
    st.markdown(
        """
        <style>
        @media (max-width: 640px) {
            .cdt-scroll-top {
                position: fixed;
                bottom: 24px;
                right: 20px;
                z-index: 9999;
                background: #1e3a5f;
                color: #ffffff;
                border-radius: 50%;
                width: 48px;
                height: 48px;
                font-size: 22px;
                font-weight: bold;
                text-align: center;
                line-height: 48px;
                text-decoration: none;
                box-shadow: 0 4px 12px rgba(0,0,0,0.35);
                display: block;
            }
            .cdt-scroll-top:hover { background: #2563eb; color: #fff; }
        }
        @media (min-width: 641px) { .cdt-scroll-top { display: none; } }
        </style>
        <a class="cdt-scroll-top" href="#" onclick="window.scrollTo(0,0);return false;"
           title="Ke atas">↑</a>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------
def _ensure_authenticated() -> bool:
    """Render password form when needed; return True if user is authenticated."""
    expected = config.RESEARCHER_PASSWORD
    if expected is None:
        st.error(
            "Mode peneliti tidak aktif. Setel `CDT_RESEARCHER_PASSWORD` pada "
            "lingkungan server lalu muat ulang halaman."
        )
        st.stop()
        return False

    if st.session_state.get("researcher_authed"):
        return True

    st.title("Mode Peneliti")
    st.caption(
        "Halaman ini hanya untuk peneliti dan penguji tesis. "
        "Masukkan kata sandi penelitian untuk melanjutkan."
    )
    with st.form("researcher_auth_form"):
        pwd = st.text_input("Kata Sandi Peneliti", type="password", max_chars=128)
        submitted = st.form_submit_button(
            "Masuk", type="primary", use_container_width=True,
        )
    if submitted:
        if pwd == expected:
            st.session_state["researcher_authed"] = True
            st.rerun()
        else:
            st.error("Kata sandi salah.")
    st.stop()
    return False


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def _section_summary(summary: dict) -> None:
    st.subheader("Ringkasan Kohort UAT")
    st.caption(
        "Indikator utama keseluruhan partisipan UAT. Skor DEI menggunakan "
        "nilai mutlak (|DEI|) untuk merefleksikan kekuatan bias terlepas dari arah."
    )

    excluded = summary.get("excluded_non_participants", 0)
    if excluded:
        st.info(
            f"Disaring otomatis: **{excluded} pengguna non-partisipan** (mis. "
            "akun admin/peneliti, residu uji legacy) dikecualikan agar "
            "statistik kohort tidak terdistorsi. Filter berbasis konsen / "
            "profil registrasi / kredensial autentikasi.",
            icon="🛡️",
        )

    row1 = responsive_columns(4, n_mobile=2)
    row1[0].metric("Total Pengguna", summary["total_users"])
    row1[1].metric("Total Sesi", summary["total_sessions"])
    row1[2].metric("Pengguna ≥3 Sesi", summary["users_with_min_3_sessions"])
    row1[3].metric(
        "Kelengkapan UAT",
        f"{summary['completion_rate'] * 100:.1f}%",
        help="Proporsi pengguna yang menyelesaikan minimal 3 sesi.",
    )

    row2 = responsive_columns(4, n_mobile=2)
    row2[0].metric("Rata-rata DEI", f"{summary['mean_dei']:.3f}")
    row2[1].metric("Rata-rata OCS", f"{summary['mean_ocs']:.3f}")
    row2[2].metric("Rata-rata LAI", f"{summary['mean_lai']:.3f}")
    row2[3].metric(
        "Rata-rata Stabilitas",
        f"{summary['mean_stability_index']:.3f}",
        help="Stability Index rata-rata kohort (0–1).",
    )

    with st.expander("Detail tambahan"):
        st.write({
            "users_with_consent": summary["users_with_consent"],
            "users_with_survey": summary["users_with_survey"],
            "sd_dei": summary["sd_dei"],
            "sd_ocs": summary["sd_ocs"],
            "sd_lai": summary["sd_lai"],
            "excluded_non_participants": excluded,
        })


def _section_users_table(users_rows: list[dict]) -> None:
    st.subheader("Tabel Peserta")
    st.caption(
        "Satu baris per pengguna, mencakup demografi, hasil onboarding, "
        "ringkasan survei pasca-sesi, dan vektor CDT terkini. "
        "Kolom CDT ditampilkan sebagai progress bar (skala 0–1)."
    )
    if not users_rows:
        st.info("Belum ada pengguna terdaftar.")
        return
    df = pd.DataFrame(users_rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "user_id": st.column_config.NumberColumn("ID"),
            "session_count": st.column_config.NumberColumn("Jumlah Sesi"),
            "cdt_overconfidence": st.column_config.ProgressColumn(
                "CDT OC (Keyakinan Berlebih)",
                min_value=0.0,
                max_value=1.0,
                format="%.3f",
            ),
            "cdt_disposition": st.column_config.ProgressColumn(
                "CDT DEI (Efek Disposisi)",
                min_value=0.0,
                max_value=1.0,
                format="%.3f",
            ),
            "cdt_loss_aversion": st.column_config.ProgressColumn(
                "CDT LAI (Aversi Kerugian)",
                min_value=0.0,
                max_value=1.0,
                format="%.3f",
            ),
            "stability_index": st.column_config.NumberColumn(
                "Stability", format="%.3f",
            ),
            "risk_preference": st.column_config.NumberColumn(
                "Pref. Risiko", format="%.3f",
            ),
        },
    )
    st.download_button(
        label="Unduh Tabel Peserta (CSV)",
        data=_csv_bytes(users_rows),
        file_name="cohort_users.csv",
        mime="text/csv",
        key="dl_users_table",
    )


def _section_distributions(sessions_rows: list[dict]) -> None:
    st.subheader("Distribusi Bias")
    st.caption(
        "Histogram intensitas bias seluruh sesi UAT dengan overlay KDE "
        "(kernel triangular).  Batang diwarnai per zona keparahan; garis vertikal "
        "menandai ambang ringan/sedang/berat dari `config.py`."
    )
    if not sessions_rows:
        st.info("Belum ada sesi tersimpan untuk divisualisasikan.")
        return

    dei_vals = [abs(r["dei"]) for r in sessions_rows if r["dei"] is not None]
    ocs_vals = [r["ocs"] for r in sessions_rows if r["ocs"] is not None]
    lai_vals = [r["lai"] for r in sessions_rows if r["lai"] is not None]

    cols = responsive_columns(3, n_mobile=1)
    for col, title, values, thresholds in (
        (cols[0], "DEI (|DEI|)", dei_vals,
         (config.DEI_MILD, config.DEI_MODERATE, config.DEI_SEVERE)),
        (cols[1], "OCS", ocs_vals,
         (config.OCS_MILD, config.OCS_MODERATE, config.OCS_SEVERE)),
        (cols[2], "LAI", lai_vals,
         (config.LAI_MILD, config.LAI_MODERATE, config.LAI_SEVERE)),
    ):
        with col:
            if not values:
                st.caption(f"Tidak ada data {title}.")
                continue

            arr = np.array(values, dtype=float)
            n = len(arr)
            v_min, v_max = float(arr.min()), float(arr.max())
            span = max(v_max - v_min, 1e-6)
            t0, t1, t2 = thresholds

            # Pre-bin for per-severity bar coloring.
            bins_lo = max(0.0, v_min - 0.05 * span)
            bins_hi = v_max + 0.1 * span
            n_bins = 20
            bin_edges = np.linspace(bins_lo, bins_hi, n_bins + 1)
            bin_width = float(bin_edges[1] - bin_edges[0])
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
            counts, _ = np.histogram(arr, bins=bin_edges)
            density = counts / (n * bin_width) if n > 0 else counts.astype(float)

            def _sev_color(x: float) -> str:
                if x < t0:
                    return _NO_BIAS_COLOR
                elif x < t1:
                    return SEVERITY_COLORS["mild"]
                elif x < t2:
                    return SEVERITY_COLORS["moderate"]
                return SEVERITY_COLORS["severe"]

            bar_colors = [_sev_color(bc) for bc in bin_centers.tolist()]

            # KDE on a fine grid.
            x_grid = np.linspace(bins_lo, bins_hi + 0.05 * span, 300)
            kde = kde_values(values, x_grid)

            # Subplots: row 1 = boxplot, row 2 = histogram + KDE.
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                row_heights=[0.2, 0.8],
                vertical_spacing=0.03,
            )

            # Row 1: horizontal box plot.
            fig.add_trace(go.Box(
                x=arr.tolist(),
                orientation="h",
                marker_color=SEVERITY_COLORS["mild"],
                line_color="#555",
                showlegend=False,
                name=title,
                boxpoints=False,
            ), row=1, col=1)

            # Row 2: severity-coloured bar histogram.
            fig.add_trace(go.Bar(
                x=bin_centers.tolist(),
                y=density.tolist(),
                width=[bin_width] * n_bins,
                marker=dict(
                    color=bar_colors,
                    line=dict(color="rgba(0,0,0,0.1)", width=0.5),
                ),
                name="Distribusi",
                showlegend=False,
                opacity=0.85,
            ), row=2, col=1)

            # Row 2: KDE overlay.
            fig.add_trace(go.Scatter(
                x=x_grid.tolist(),
                y=kde.tolist(),
                mode="lines",
                line=dict(color="black", width=2),
                name="KDE",
                showlegend=False,
            ), row=2, col=1)

            # Threshold vlines (row 2 only).
            for sev, val in zip(("mild", "moderate", "severe"), thresholds):
                fig.add_vline(
                    x=val,
                    line=dict(
                        color=SEVERITY_COLORS[sev], width=1.5, dash="dash",
                    ),
                    row=2, col=1,
                    annotation_text=sev,
                    annotation_position="top right",
                    annotation_font=dict(size=9),
                    annotation_bgcolor="rgba(255,255,255,0.8)",
                    annotation_bordercolor=SEVERITY_COLORS[sev],
                    annotation_borderwidth=1,
                    annotation_borderpad=2,
                )

            # Annotation n / μ / σ.
            mean_v = float(np.mean(arr))
            sd_v = float(np.std(arr, ddof=1)) if n >= 2 else 0.0
            fig.add_annotation(
                text=f"n={n}  μ={mean_v:.3f}  σ={sd_v:.3f}",
                xref="paper", yref="paper",
                x=0.99, y=0.99,
                showarrow=False,
                xanchor="right", yanchor="top",
                bgcolor="rgba(255,255,255,0.88)",
                bordercolor="#aaa",
                borderwidth=1,
                font=dict(size=9),
            )

            fig.update_layout(
                title=title,
                showlegend=False,
                bargap=0.02,
            )
            apply_chart_theme(
                fig,
                height=400,
                mobile_legend="hide",
                margin=dict(l=10, r=10, t=56, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)


def _section_trajectory(snapshots_rows: list[dict]) -> None:
    st.subheader("Trajektori CDT Longitudinal")
    st.caption(
        "Setiap garis adalah satu pengguna (opacity rendah). Garis tebal hitam = "
        "rata-rata kohort; pita abu-abu = ±1σ. Warna individu menunjukkan kuartil "
        "intensitas akhir."
    )
    if not snapshots_rows:
        st.info("Belum ada snapshot CDT yang tersedia.")
        return

    df = pd.DataFrame(snapshots_rows)
    bias_options = {
        "Bias Keyakinan Berlebih (CDT OC)": "cdt_overconfidence",
        "Efek Disposisi (CDT DEI)": "cdt_disposition",
        "Menghindari Kerugian (CDT LAI)": "cdt_loss_aversion",
    }
    view_mode = st.radio(
        "Tampilan",
        options=list(bias_options.keys()) + ["Tampilan kohort saja"],
        horizontal=True,
        key="researcher_traj_bias",
    )
    show_individual = view_mode != "Tampilan kohort saja"

    fig = go.Figure()

    if view_mode == "Tampilan kohort saja":
        # Show cohort mean ± 1σ for all three biases on one chart.
        all_bias_cols = {
            "CDT OC": ("cdt_overconfidence", "#3b82f6"),
            "CDT DEI": ("cdt_disposition", "#22c55e"),
            "CDT LAI": ("cdt_loss_aversion", "#f59e0b"),
        }
        session_nums_all = sorted(df["session_number"].unique().tolist())
        for bias_name, (bias_col, color) in all_bias_cols.items():
            means, uppers, lowers, valid_sns = [], [], [], []
            for sn in session_nums_all:
                sn_vals = df[df["session_number"] == sn][bias_col].dropna().tolist()
                if sn_vals:
                    m = float(np.mean(sn_vals))
                    s = float(np.std(sn_vals, ddof=1)) if len(sn_vals) >= 2 else 0.0
                    means.append(m)
                    uppers.append(m + s)
                    lowers.append(m - s)
                    valid_sns.append(sn)
            if not valid_sns:
                continue
            band_x = valid_sns + valid_sns[::-1]
            band_y = uppers + lowers[::-1]
            fig.add_trace(go.Scatter(
                x=band_x, y=band_y,
                fill="toself",
                fillcolor=_hex_to_rgba(color, 0.12),
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                name=f"{bias_name} ±1σ",
            ))
            fig.add_trace(go.Scatter(
                x=valid_sns, y=means,
                mode="lines+markers",
                line=dict(color=color, width=2.5),
                marker=dict(size=7),
                name=bias_name,
            ))
    else:
        bias_col = bias_options[view_mode]
        user_labels = sorted(df["username"].dropna().unique().tolist())
        selected_user = st.selectbox(
            "Sorot pengguna (opsional)",
            options=["(tidak ada)"] + user_labels,
            index=0,
            key="researcher_traj_user",
        )

        # Quartile assignment by final-session intensity.
        final_vals: dict[str, float] = {}
        for username, group in df.groupby("username"):
            sorted_grp = group.sort_values("session_number")
            col_vals = sorted_grp[bias_col].dropna()
            if not col_vals.empty:
                final_vals[str(username)] = float(col_vals.iloc[-1])

        fv_list = sorted(final_vals.values())
        if len(fv_list) >= 4:
            q25 = float(np.percentile(fv_list, 25))
            q50 = float(np.percentile(fv_list, 50))
            q75 = float(np.percentile(fv_list, 75))
        else:
            q25 = q50 = q75 = float(np.median(fv_list)) if fv_list else 0.5

        def _quartile_idx(v: float) -> int:
            if v <= q25:
                return 0
            if v <= q50:
                return 1
            if v <= q75:
                return 2
            return 3

        shown_quartiles: set[int] = set()
        for username, group in df.groupby("username"):
            fv = final_vals.get(str(username), 0.0)
            qi = _quartile_idx(fv)
            is_focus = (
                selected_user != "(tidak ada)" and username == selected_user
            )
            opacity = 1.0 if is_focus else 0.18
            width = 3 if is_focus else 1.2
            show_legend = qi not in shown_quartiles
            shown_quartiles.add(qi)
            fig.add_trace(go.Scatter(
                x=group["session_number"].tolist(),
                y=group[bias_col].tolist(),
                mode="lines+markers",
                name=_Q_LABELS[qi],
                line=dict(width=width, color=_Q_COLORS[qi]),
                opacity=opacity,
                legendgroup=f"q{qi}",
                showlegend=show_legend,
                marker=dict(size=3),
            ))

        # Cohort mean ± 1σ band.
        session_nums = sorted(df["session_number"].unique().tolist())
        valid_sns, means, uppers, lowers = [], [], [], []
        for sn in session_nums:
            sn_vals = df[df["session_number"] == sn][bias_col].dropna().tolist()
            if sn_vals:
                m = float(np.mean(sn_vals))
                s = float(np.std(sn_vals, ddof=1)) if len(sn_vals) >= 2 else 0.0
                valid_sns.append(sn)
                means.append(m)
                uppers.append(m + s)
                lowers.append(m - s)
        if valid_sns:
            fig.add_trace(go.Scatter(
                x=valid_sns + valid_sns[::-1],
                y=uppers + lowers[::-1],
                fill="toself",
                fillcolor="rgba(100,100,100,0.13)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=True,
                name="±1σ kohort",
                legendgroup="cohort",
            ))
            fig.add_trace(go.Scatter(
                x=valid_sns,
                y=means,
                mode="lines+markers",
                line=dict(color="black", width=3),
                marker=dict(size=8, color="black"),
                name="Rata-rata Kohort",
                legendgroup="cohort",
            ))

    fig.update_xaxes(title_text="Nomor Sesi")
    fig.update_yaxes(title_text="Intensitas (0–1)", range=[0, 1])
    apply_chart_theme(fig, height=440, mobile_legend="top")
    st.plotly_chart(fig, use_container_width=True)


def _section_correlation_heatmap(sessions_rows: list[dict]) -> None:
    st.subheader("Korelasi Inter-Bias")
    st.caption(
        "Matriks korelasi Pearson r antar tiga dimensi bias (DEI, OCS, LAI) "
        "dihitung lintas semua sesi UAT.  Asterisk menunjukkan signifikansi "
        "statistik (* p<0,05  ** p<0,01  *** p<0,001) berdasarkan uji-t "
        "dengan aproksimasi normal."
    )
    if not sessions_rows:
        st.info("Belum ada sesi tersimpan untuk divisualisasikan.")
        return

    # Build aligned (DEI, OCS, LAI) triplets — only sessions with all three.
    dei_v, ocs_v, lai_v = [], [], []
    for r in sessions_rows:
        dei = abs(r["dei"]) if r["dei"] is not None else None
        ocs = r["ocs"]
        lai = r["lai"]
        if all(v is not None for v in (dei, ocs, lai)):
            dei_v.append(float(dei))  # type: ignore[arg-type]
            ocs_v.append(float(ocs))  # type: ignore[arg-type]
            lai_v.append(float(lai))  # type: ignore[arg-type]

    n_aligned = len(dei_v)
    if n_aligned < 2:
        st.info("Data sesi belum cukup untuk menghitung korelasi inter-bias.")
        return

    labels = ["DEI", "OCS", "LAI"]
    vectors = [dei_v, ocs_v, lai_v]
    n_bias = 3

    r_matrix: list[list[float]] = [[0.0] * n_bias for _ in range(n_bias)]
    p_matrix: list[list[float | None]] = [[None] * n_bias for _ in range(n_bias)]
    for i in range(n_bias):
        for j in range(n_bias):
            if i == j:
                r_matrix[i][j] = 1.0
                p_matrix[i][j] = 0.0
            else:
                r, p = pearson_with_p(vectors[i], vectors[j])
                r_matrix[i][j] = r if r is not None else 0.0
                p_matrix[i][j] = p

    text_matrix = [
        [
            f"{r_matrix[i][j]:.2f}{significance_stars(p_matrix[i][j])}"
            for j in range(n_bias)
        ]
        for i in range(n_bias)
    ]

    fig = go.Figure(go.Heatmap(
        z=r_matrix,
        x=labels,
        y=labels,
        text=text_matrix,
        texttemplate="%{text}",
        colorscale="RdBu",
        zmid=0.0,
        zmin=-1.0,
        zmax=1.0,
        colorbar=dict(title="r", thickness=14),
        textfont=dict(size=14),
    ))
    fig.update_layout(title=f"Korelasi Inter-Bias (n sesi = {n_aligned})")
    apply_chart_theme(
        fig, height=360,
        mobile_legend="hide",
        margin=dict(l=40, r=40, t=60, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Korelasi tinggi antar bias menunjukkan pola kognisi yang ko-terjadi "
        "secara konsisten, mendukung validitas konstruk model CDT multi-dimensi. "
        "Nilai di diagonal selalu 1 (korelasi diri)."
    )


def _section_cohort_progression(progression_rows: list[dict]) -> None:
    st.subheader("Progresi Kohort per Sesi")
    st.caption(
        "Rata-rata intensitas bias kohort per nomor sesi (1 = pertama, dst.). "
        "Pita = 95% bootstrap CI (1 000 resampel). Temuan longitudinal utama."
    )
    if not progression_rows:
        st.info("Belum ada data progres sesi.")
        return

    # Pivot: bias → {session_number: [values]}
    bias_groups: dict[str, dict[int, list[float]]] = {
        k: {} for k in _BIAS_META
    }
    for row in progression_rows:
        bias = row["bias"]
        if bias not in bias_groups:
            continue
        sn = row["session_number"]
        bias_groups[bias][sn] = row["values"]

    fig = go.Figure()
    for bias, (display_name, color) in _BIAS_META.items():
        groups = bias_groups[bias]
        if not groups:
            continue
        ci_data = bootstrap_ci(groups, n_resamples=1000)
        sess_nums = sorted(ci_data.keys())
        means_b = [ci_data[s][0] for s in sess_nums]
        lowers_b = [ci_data[s][1] for s in sess_nums]
        uppers_b = [ci_data[s][2] for s in sess_nums]

        # CI band.
        fig.add_trace(go.Scatter(
            x=sess_nums + sess_nums[::-1],
            y=uppers_b + lowers_b[::-1],
            fill="toself",
            fillcolor=_hex_to_rgba(color, 0.15),
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False,
            name=f"{display_name} CI",
        ))
        # Mean line.
        fig.add_trace(go.Scatter(
            x=sess_nums,
            y=means_b,
            mode="lines+markers",
            line=dict(color=color, width=2.5),
            marker=dict(size=8, color=color),
            name=display_name,
        ))

    fig.update_xaxes(
        title_text="Nomor Sesi",
        tickmode="linear",
        dtick=1,
    )
    fig.update_yaxes(title_text="Intensitas rata-rata (0–1)", range=[0, 1])
    apply_chart_theme(fig, height=420, mobile_legend="top")
    st.plotly_chart(fig, use_container_width=True)

    # Show sample sizes per session.
    n_by_sess: dict[int, int] = {}
    for row in progression_rows:
        sn = row["session_number"]
        n_by_sess[sn] = max(n_by_sess.get(sn, 0), row["n"])
    if n_by_sess:
        n_info = "  |  ".join(
            f"Sesi {sn}: n={n}" for sn, n in sorted(n_by_sess.items())
        )
        st.caption(f"Ukuran sampel: {n_info}")


def _section_survey_vs_observed(users_rows: list[dict]) -> None:
    st.subheader("Survei vs. Hasil Observasi")
    st.caption(
        "Validasi apakah respons survei awal (prior) memprediksi intensitas "
        "bias yang teramati melalui simulasi. Garis penuh = regresi OLS + "
        "95% CI; garis putus-putus abu-abu = y=x (prediksi sempurna)."
    )

    bias_specs = [
        ("DEI", ("onboarding_dei_q1", "onboarding_dei_q2", "onboarding_dei_q3"),
         "cdt_disposition"),
        ("OCS", ("onboarding_ocs_q1", "onboarding_ocs_q2", "onboarding_ocs_q3"),
         "cdt_overconfidence"),
        ("LAI", ("onboarding_lai_q1", "onboarding_lai_q2", "onboarding_lai_q3"),
         "cdt_loss_aversion"),
    ]

    cols = responsive_columns(3, n_mobile=1)
    for col, (label, q_keys, observed_key) in zip(cols, bias_specs):
        xs_raw: list[float] = []
        ys: list[float] = []
        for r in users_rows:
            qs = [r.get(k) for k in q_keys]
            obs = r.get(observed_key)
            if any(q is None for q in qs) or obs is None:
                continue
            prior = (sum(qs) / 3.0 - 1.0) / 4.0  # Likert 1–5 → [0, 1]
            xs_raw.append(prior)
            ys.append(float(obs))

        with col:
            if len(xs_raw) < 2:
                st.caption(f"Data {label} belum cukup untuk korelasi.")
                continue

            # Jitter ties: add ±0.005 noise to xs when ≥2 share the same value.
            x_count = Counter(round(x, 4) for x in xs_raw)
            rng_j = np.random.default_rng(seed=77)
            xs_j = [
                x + float(rng_j.uniform(-0.005, 0.005))
                if x_count[round(x, 4)] >= 2 else x
                for x in xs_raw
            ]

            r_val = _pearson(xs_raw, ys)
            r_text = f"r = {r_val:.3f}" if r_val is not None else "r = —"

            fig = go.Figure()

            # Quadrant shading (x = prior, y = observed; midpoint 0.5).
            mid = 0.5
            quad_specs = [
                (0, 0, mid, mid, "rgba(34,197,94,0.07)"),    # BL consistent
                (mid, mid, 1, 1, "rgba(34,197,94,0.07)"),    # TR consistent
                (0, mid, mid, 1, "rgba(239,68,68,0.07)"),    # TL overestimated
                (mid, 0, 1, mid, "rgba(59,130,246,0.07)"),   # BR underestimated
            ]
            quad_labels = [
                (mid / 2, mid / 2, "Konsisten\n(rendah)"),
                (mid + mid / 2, mid + mid / 2, "Konsisten\n(tinggi)"),
                (mid / 2, mid + mid / 2, "Survei\nlebih tinggi"),
                (mid + mid / 2, mid / 2, "Survei\nlebih rendah"),
            ]
            for x0, y0, x1, y1, fc in quad_specs:
                fig.add_shape(
                    type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                    fillcolor=fc, line_width=0,
                )
            for lx, ly, ltxt in quad_labels:
                fig.add_annotation(
                    x=lx, y=ly, text=ltxt.replace("\n", "<br>"),
                    showarrow=False,
                    font=dict(size=8, color="#888"),
                    xanchor="center", yanchor="middle",
                )

            # Identity diagonal y = x.
            fig.add_shape(
                type="line", x0=0, y0=0, x1=1, y1=1,
                line=dict(color="#aaa", width=1.5, dash="dash"),
            )

            # OLS regression + 95 % CI band.
            x_grid = np.linspace(0.0, 1.0, 200)
            y_fit, lower, upper = ols_confidence_band(
                xs_raw, ys, x_grid, alpha=0.05,
            )
            fig.add_trace(go.Scatter(
                x=x_grid.tolist() + x_grid[::-1].tolist(),
                y=upper.tolist() + lower[::-1].tolist(),
                fill="toself",
                fillcolor="rgba(59,130,246,0.12)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                name="CI 95%",
            ))
            slope, intercept = ols_fit(xs_raw, ys)
            fig.add_trace(go.Scatter(
                x=x_grid.tolist(),
                y=y_fit.tolist(),
                mode="lines",
                line=dict(color="#1d4ed8", width=2),
                name=f"OLS (slope={slope:.2f})",
            ))

            # Scatter points (jittered).
            fig.add_trace(go.Scatter(
                x=xs_j, y=ys,
                mode="markers",
                marker=dict(
                    size=9, color=SEVERITY_COLORS["mild"],
                    opacity=0.75, line=dict(color="white", width=0.5),
                ),
                name=label,
                showlegend=False,
            ))

            fig.update_xaxes(title_text="Prior survei (0–1)", range=[0, 1])
            fig.update_yaxes(title_text="Intensitas teramati (0–1)", range=[0, 1])
            fig.update_layout(title=f"{label} ({r_text}, n={len(xs_raw)})")
            apply_chart_theme(fig, height=340, mobile_legend="hide")
            st.plotly_chart(fig, use_container_width=True)


def _section_model_performance() -> None:
    st.subheader("Performa Model ML")
    perf = load_model_performance()
    if not perf["available"]:
        st.warning(
            "Berkas performa model tidak ditemukan di folder `reports/`. "
            "Jalankan `python scripts/run_ml_validation.py` terlebih dahulu, "
            "lalu muat ulang halaman ini."
        )
        return

    summary = perf["summary"] or {}
    accuracy = summary.get("overall_accuracy")
    n_train = summary.get("n_training_samples")

    cls_rows = perf["classification_report"] or []
    macro_f1 = None
    weighted_f1 = None
    for row in cls_rows:
        label_str = (row.get("kelas") or "").lower()
        if "makro" in label_str:
            try:
                macro_f1 = float(row.get("f1_score") or 0.0)
            except ValueError:
                macro_f1 = None
        elif "tertimbang" in label_str:
            try:
                weighted_f1 = float(row.get("f1_score") or 0.0)
            except ValueError:
                weighted_f1 = None

    cols = responsive_columns(4, n_mobile=2)
    cols[0].metric(
        "Akurasi", f"{accuracy:.3f}" if accuracy is not None else "—",
    )
    cols[1].metric(
        "F1 Makro", f"{macro_f1:.3f}" if macro_f1 is not None else "—",
    )
    cols[2].metric(
        "F1 Tertimbang",
        f"{weighted_f1:.3f}" if weighted_f1 is not None else "—",
    )
    cols[3].metric(
        "Sampel Latih", n_train if n_train is not None else "—",
    )

    if cls_rows:
        st.markdown("**Laporan Klasifikasi per Kelas**")
        st.dataframe(
            pd.DataFrame(cls_rows),
            use_container_width=True,
            hide_index=True,
        )

    # Feature importance: prefer live Plotly chart from JSON, fall back to PNG.
    feature_importances = summary.get("feature_importances")
    feature_names = summary.get("feature_names", [])

    if feature_importances and feature_names and len(feature_importances) == len(feature_names):
        st.markdown("**Pentingnya Fitur (Feature Importance)**")
        pairs = sorted(
            zip(feature_names, feature_importances),
            key=lambda p: p[1],
        )
        fig_fi = go.Figure(go.Bar(
            x=[p[1] for p in pairs],
            y=[p[0] for p in pairs],
            orientation="h",
            marker_color="#3b82f6",
        ))
        fig_fi.update_layout(
            xaxis_title="Importance",
            margin=dict(l=10, r=10, t=10, b=10),
        )
        apply_chart_theme(fig_fi, height=max(300, 20 * len(pairs)))
        st.plotly_chart(fig_fi, use_container_width=True)
    elif perf["feature_importance_path"]:
        st.markdown("**Pentingnya Fitur (Feature Importance)**")
        st.image(perf["feature_importance_path"], use_container_width=True)

    # Confusion matrix.
    confusion_matrix_data = summary.get("confusion_matrix")
    if confusion_matrix_data:
        st.markdown("**Matriks Kebingungan**")
        cm = confusion_matrix_data
        classes = list(cm.keys()) if isinstance(cm, dict) else []
        if classes:
            z_mat = [[cm[r].get(c, 0) for c in classes] for r in classes]
            fig_cm = go.Figure(go.Heatmap(
                z=z_mat,
                x=classes,
                y=classes,
                colorscale="Blues",
                text=[[str(v) for v in row] for row in z_mat],
                texttemplate="%{text}",
            ))
            fig_cm.update_layout(
                xaxis_title="Prediksi",
                yaxis_title="Aktual",
                margin=dict(l=60, r=10, t=20, b=60),
            )
            apply_chart_theme(fig_cm, height=340)
            st.plotly_chart(fig_cm, use_container_width=True)
    else:
        st.caption("Matriks kebingungan tidak tersedia di laporan ini.")

    if perf["decision_tree_path"]:
        with st.expander("Pohon Keputusan"):
            st.image(perf["decision_tree_path"], use_container_width=True)

    if perf["generated_at"]:
        st.caption(f"Dihasilkan pada: {perf['generated_at']}")
    if summary.get("used_synthetic_data"):
        st.info(
            "Catatan: model dilatih menggunakan data sintetis karena jumlah "
            "rekaman UAT belum mencapai ambang minimum."
        )


def _section_uat_surveys(
    uat_rows: list[dict],
    post_session_rows: list[dict],
) -> None:
    """Render the UAT survey + post-session survey inspection tab."""
    st.subheader("Survei UAT")
    st.caption(
        "Riwayat lengkap setiap kiriman survei. Tidak ada penimpaan: setiap "
        "submit menjadi baris baru. Untuk analisis tesis, gunakan kiriman "
        "**terbaru per pengguna** (ambil baris dengan `submission_index` "
        "tertinggi per `user_id`)."
    )

    # --- KPIs row ---
    n_uat_total = len(uat_rows)
    n_uat_users = len({r["user_id"] for r in uat_rows}) if uat_rows else 0
    sus_scores = [r["sus_score"] for r in uat_rows if r.get("sus_score") is not None]
    avg_sus = sum(sus_scores) / len(sus_scores) if sus_scores else None

    # Latest-per-user SUS for the recommended analysis aggregate
    latest_per_user: dict[int, dict] = {}
    for r in uat_rows:
        prev = latest_per_user.get(r["user_id"])
        if prev is None or r["submission_index"] > prev["submission_index"]:
            latest_per_user[r["user_id"]] = r
    latest_sus = [
        r["sus_score"] for r in latest_per_user.values()
        if r.get("sus_score") is not None
    ]
    avg_latest_sus = (
        sum(latest_sus) / len(latest_sus) if latest_sus else None
    )

    n_post_total = len(post_session_rows)
    n_post_users = (
        len({r["user_id"] for r in post_session_rows}) if post_session_rows else 0
    )

    cols = responsive_columns(4, n_mobile=2)
    cols[0].metric("Kiriman UAT", n_uat_total)
    cols[1].metric("Pengguna unik (UAT)", n_uat_users)
    cols[2].metric(
        "Rata-rata SUS (semua kiriman)",
        f"{avg_sus:.1f}" if avg_sus is not None else "—",
    )
    cols[3].metric(
        "Rata-rata SUS (terbaru per pengguna)",
        f"{avg_latest_sus:.1f}" if avg_latest_sus is not None else "—",
        help=(
            "Aggregate yang direkomendasikan untuk analisis tesis. "
            "Mengambil 1 kiriman terbaru per pengguna lalu merata-ratakan."
        ),
    )

    # --- UAT submissions table ---
    st.markdown("**Riwayat Submit UAT (SUS + Pertanyaan Terbuka)**")
    if uat_rows:
        df_uat = pd.DataFrame(uat_rows)
        st.dataframe(
            df_uat,
            use_container_width=True,
            hide_index=True,
            column_config={
                "user_id": st.column_config.NumberColumn("ID"),
                "submission_index": st.column_config.NumberColumn("Kiriman ke-"),
                "sus_score": st.column_config.NumberColumn(
                    "Skor SUS", format="%.1f",
                ),
                "open_confusing": st.column_config.TextColumn(
                    "Membingungkan", width="medium",
                ),
                "open_useful": st.column_config.TextColumn(
                    "Berguna / Saran", width="medium",
                ),
            },
        )
        st.download_button(
            label="Unduh Survei UAT (CSV — riwayat lengkap)",
            data=_csv_bytes(uat_rows),
            file_name="research_uat_feedback.csv",
            mime="text/csv",
            key="dl_uat_feedback",
            use_container_width=True,
        )
    else:
        st.info("Belum ada kiriman UAT.")

    st.divider()

    # --- Post-session surveys ---
    st.markdown("**Survei Pasca-Sesi (Self-Assessment)**")
    st.caption(
        "Satu baris per (pengguna × sesi). Skor `feedback_usefulness` "
        "(1–5) dan tiga skor self-awareness bias dipakai untuk validasi "
        "metakognitif di Bab VI."
    )
    cols2 = responsive_columns(2, n_mobile=2)
    cols2[0].metric("Total Kiriman", n_post_total)
    cols2[1].metric("Pengguna unik", n_post_users)

    if post_session_rows:
        df_post = pd.DataFrame(post_session_rows)
        st.dataframe(
            df_post,
            use_container_width=True,
            hide_index=True,
            column_config={
                "user_id": st.column_config.NumberColumn("ID"),
                "self_overconfidence": st.column_config.NumberColumn("Self-OC"),
                "self_disposition": st.column_config.NumberColumn("Self-DEI"),
                "self_loss_aversion": st.column_config.NumberColumn("Self-LAI"),
                "feedback_usefulness": st.column_config.NumberColumn(
                    "Useful (1–5)",
                ),
            },
        )
        st.download_button(
            label="Unduh Survei Pasca-Sesi (CSV)",
            data=_csv_bytes(post_session_rows),
            file_name="research_post_session_surveys.csv",
            mime="text/csv",
            key="dl_post_session",
            use_container_width=True,
        )
    else:
        st.info("Belum ada kiriman survei pasca-sesi.")


def _section_bulk_export(
    users_rows: list[dict],
    sessions_rows: list[dict],
    snapshots_rows: list[dict],
    uat_rows: list[dict],
    post_session_rows: list[dict],
) -> None:
    st.subheader("Ekspor Massal")
    st.caption(
        "Unduh keseluruhan data UAT untuk analisis statistik di luar aplikasi. "
        "Survei UAT dan pasca-sesi diekspor sebagai riwayat lengkap (semua "
        "kiriman; gunakan `submission_index` tertinggi per pengguna untuk "
        "agregat terbaru)."
    )
    row1 = responsive_columns(3, n_mobile=1)
    with row1[0]:
        st.download_button(
            label="Semua Pengguna (CSV)",
            data=_csv_bytes(users_rows),
            file_name="research_all_users.csv",
            mime="text/csv",
            key="dl_all_users",
            disabled=not users_rows,
            use_container_width=True,
        )
    with row1[1]:
        st.download_button(
            label="Semua Sesi (CSV)",
            data=_csv_bytes(sessions_rows),
            file_name="research_all_sessions.csv",
            mime="text/csv",
            key="dl_all_sessions",
            disabled=not sessions_rows,
            use_container_width=True,
        )
    with row1[2]:
        st.download_button(
            label="Snapshot CDT (CSV)",
            data=_csv_bytes(snapshots_rows),
            file_name="research_cdt_snapshots.csv",
            mime="text/csv",
            key="dl_all_snapshots",
            disabled=not snapshots_rows,
            use_container_width=True,
        )

    row2 = responsive_columns(2, n_mobile=1)
    with row2[0]:
        st.download_button(
            label="Survei UAT (CSV — riwayat lengkap)",
            data=_csv_bytes(uat_rows),
            file_name="research_uat_feedback.csv",
            mime="text/csv",
            key="dl_bulk_uat_feedback",
            disabled=not uat_rows,
            use_container_width=True,
        )
    with row2[1]:
        st.download_button(
            label="Survei Pasca-Sesi (CSV)",
            data=_csv_bytes(post_session_rows),
            file_name="research_post_session_surveys.csv",
            mime="text/csv",
            key="dl_bulk_post_session",
            disabled=not post_session_rows,
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def render_researcher_page() -> None:
    """Render the full researcher view (after auth)."""
    inject_custom_css()
    st.markdown(
        """
        <style>
        div[data-testid="stMetricLabel"] > div {
            white-space: normal;
            overflow: visible;
            text-overflow: clip;
            line-height: 1.2;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if not _ensure_authenticated():
        return

    render_mobile_banner()
    _mobile_scroll_top()
    st.title("Mode Peneliti — Inspeksi UAT")
    st.caption(
        f"Akses berhasil. Waktu server: {fmt_datetime_wib(__import__('datetime').datetime.now(__import__('datetime').timezone.utc))}."
    )

    # All exports filtered to qualified participants so admin/legacy/test
    # residuals (e.g. seeded `pgjson_*` rows or the researcher_admin shell)
    # don't pollute cohort statistics or per-user tables.
    with get_session() as sess:
        summary = get_cohort_summary(sess, participants_only=True)
        users_rows = export_all_users_csv(sess, participants_only=True)
        sessions_rows = export_all_sessions_csv(sess, participants_only=True)
        snapshots_rows = export_cdt_snapshots_csv(sess, participants_only=True)
        progression_rows = compute_cohort_session_progression(sess, participants_only=True)
        uat_rows = export_uat_feedback_csv(sess, participants_only=True)
        post_session_rows = export_post_session_surveys_csv(sess, participants_only=True)

    tabs = responsive_tabs([
        "Ringkasan",
        "Peserta",
        "Distribusi",
        "Trajektori",
        "Korelasi",
        "Progresi",
        "Survei vs. Observasi",
        "Survei UAT",
        "Model ML",
        "Ekspor",
    ])

    with tabs[0]:
        _section_summary(summary)
    with tabs[1]:
        _section_users_table(users_rows)
    with tabs[2]:
        _section_distributions(sessions_rows)
    with tabs[3]:
        _section_trajectory(snapshots_rows)
    with tabs[4]:
        _section_correlation_heatmap(sessions_rows)
    with tabs[5]:
        _section_cohort_progression(progression_rows)
    with tabs[6]:
        _section_survey_vs_observed(users_rows)
    with tabs[7]:
        _section_uat_surveys(uat_rows, post_session_rows)
    with tabs[8]:
        _section_model_performance()
    with tabs[9]:
        _section_bulk_export(
            users_rows, 
            sessions_rows, 
            snapshots_rows, 
            uat_rows, 
            post_session_rows
        )


# When Streamlit auto-discovers this file under ``pages/`` and executes it as
# a script (sidebar navigation), Streamlit's ScriptRunner sets ``__name__`` to
# ``"__main__"``. Plain ``import`` from app.py keeps it as ``pages.researcher``.
if __name__ == "__main__":
    render_researcher_page()
