"""
pages/researcher.py — Mode peneliti (researcher view).

Halaman tersembunyi untuk inspeksi data UAT pada level kohort. Akses melalui
URL ``/?view=researcher`` dan dilindungi kata sandi (env var
``CDT_RESEARCHER_PASSWORD``). Tidak ada tombol navigasi di header utama.

Bagian:
    1. Ringkasan Kohort UAT
    2. Tabel Peserta
    3. Distribusi Bias (DEI / OCS / LAI)
    4. Trajektori CDT Longitudinal
    5. Survei vs. Hasil Observasi
    6. Performa Model ML
    7. Ekspor Massal CSV
"""

from __future__ import annotations

import csv
import io
import logging
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from database.connection import get_session
from modules.utils.research_export import (
    export_all_sessions_csv,
    export_all_users_csv,
    export_cdt_snapshots_csv,
    get_cohort_summary,
    load_model_performance,
)
from modules.utils.ui_helpers import (
    SEVERITY_COLORS, apply_chart_theme, fmt_datetime_wib,
)

logger = logging.getLogger(__name__)


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

    row1 = st.columns(4)
    row1[0].metric("Total Pengguna", summary["total_users"])
    row1[1].metric("Total Sesi", summary["total_sessions"])
    row1[2].metric("Pengguna ≥3 Sesi", summary["users_with_min_3_sessions"])
    row1[3].metric(
        "Tingkat Kelengkapan",
        f"{summary['completion_rate'] * 100:.1f}%",
        help="Proporsi pengguna yang menyelesaikan minimal 3 sesi.",
    )

    row2 = st.columns(4)
    row2[0].metric("Rata-rata DEI", f"{summary['mean_dei']:.3f}")
    row2[1].metric("Rata-rata OCS", f"{summary['mean_ocs']:.3f}")
    row2[2].metric("Rata-rata LAI", f"{summary['mean_lai']:.3f}")
    row2[3].metric(
        "Rata-rata Stability Index",
        f"{summary['mean_stability_index']:.3f}",
    )

    with st.expander("Detail tambahan"):
        st.write({
            "users_with_consent": summary["users_with_consent"],
            "users_with_survey": summary["users_with_survey"],
            "sd_dei": summary["sd_dei"],
            "sd_ocs": summary["sd_ocs"],
            "sd_lai": summary["sd_lai"],
        })


def _section_users_table(users_rows: list[dict]) -> None:
    st.subheader("Tabel Peserta")
    st.caption(
        "Satu baris per pengguna, mencakup demografi, hasil onboarding, "
        "ringkasan survei pasca-sesi, dan vektor CDT terkini."
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
            "cdt_overconfidence": st.column_config.NumberColumn(
                "CDT OC", format="%.3f",
            ),
            "cdt_disposition": st.column_config.NumberColumn(
                "CDT DEI", format="%.3f",
            ),
            "cdt_loss_aversion": st.column_config.NumberColumn(
                "CDT LAI", format="%.3f",
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
        "Histogram intensitas bias seluruh sesi UAT. Garis vertikal "
        "menandai ambang ringan/sedang/berat dari `config.py`."
    )
    if not sessions_rows:
        st.info("Belum ada sesi tersimpan untuk divisualisasikan.")
        return

    dei_vals = [abs(r["dei"]) for r in sessions_rows if r["dei"] is not None]
    ocs_vals = [r["ocs"] for r in sessions_rows if r["ocs"] is not None]
    lai_vals = [r["lai"] for r in sessions_rows if r["lai"] is not None]

    cols = st.columns(3)
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
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=values,
                marker=dict(color=SEVERITY_COLORS["mild"]),
                opacity=0.85,
                nbinsx=20,
                name=title,
            ))
            for sev, val in zip(("mild", "moderate", "severe"), thresholds):
                fig.add_vline(
                    x=val,
                    line=dict(color=SEVERITY_COLORS[sev], width=1.5, dash="dash"),
                    annotation_text=sev,
                    annotation_position="top right",
                )
            fig.update_layout(title=title, showlegend=False)
            apply_chart_theme(fig, height=320)
            st.plotly_chart(fig, use_container_width=True)


def _section_trajectory(snapshots_rows: list[dict]) -> None:
    st.subheader("Trajektori CDT Longitudinal")
    st.caption(
        "Setiap garis adalah satu pengguna; sumbu X = nomor sesi. "
        "Pilih bias di bawah dan opsional sorot satu pengguna."
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
    bias_label = st.radio(
        "Bias yang ditampilkan",
        options=list(bias_options.keys()),
        horizontal=True,
        key="researcher_traj_bias",
    )
    bias_col = bias_options[bias_label]

    user_labels = sorted(df["username"].dropna().unique().tolist())
    selected_user = st.selectbox(
        "Sorot pengguna (opsional)",
        options=["(tidak ada)"] + user_labels,
        index=0,
        key="researcher_traj_user",
    )

    fig = go.Figure()
    for username, group in df.groupby("username"):
        is_focus = (selected_user != "(tidak ada)" and username == selected_user)
        opacity = 1.0 if is_focus else (
            0.25 if selected_user != "(tidak ada)" else 0.65
        )
        width = 3 if is_focus else 1.5
        fig.add_trace(go.Scatter(
            x=group["session_number"],
            y=group[bias_col],
            mode="lines+markers",
            name=str(username),
            line=dict(width=width),
            opacity=opacity,
        ))
    fig.update_xaxes(title_text="Nomor Sesi")
    fig.update_yaxes(title_text="Intensitas (0–1)", range=[0, 1])
    apply_chart_theme(fig, height=420)
    st.plotly_chart(fig, use_container_width=True)


def _section_survey_vs_observed(users_rows: list[dict]) -> None:
    st.subheader("Survei vs. Hasil Observasi")
    st.caption(
        "Validasi apakah respons survei awal (prior) memprediksi intensitas "
        "bias yang teramati melalui simulasi. Skor survei dinormalisasi 0–1 "
        "dari rata-rata 3 item Likert (skala 1–5)."
    )

    bias_specs = [
        ("DEI", ("onboarding_dei_q1", "onboarding_dei_q2", "onboarding_dei_q3"),
         "cdt_disposition"),
        ("OCS", ("onboarding_ocs_q1", "onboarding_ocs_q2", "onboarding_ocs_q3"),
         "cdt_overconfidence"),
        ("LAI", ("onboarding_lai_q1", "onboarding_lai_q2", "onboarding_lai_q3"),
         "cdt_loss_aversion"),
    ]

    cols = st.columns(3)
    for col, (label, q_keys, observed_key) in zip(cols, bias_specs):
        xs: list[float] = []
        ys: list[float] = []
        for r in users_rows:
            qs = [r.get(k) for k in q_keys]
            obs = r.get(observed_key)
            if any(q is None for q in qs) or obs is None:
                continue
            prior = (sum(qs) / 3.0 - 1.0) / 4.0  # Likert 1–5 → [0, 1]
            xs.append(prior)
            ys.append(float(obs))

        with col:
            if len(xs) < 2:
                st.caption(f"Data {label} belum cukup untuk korelasi.")
                continue
            r_val = _pearson(xs, ys)
            r_text = f"r = {r_val:.3f}" if r_val is not None else "r = —"
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="markers",
                marker=dict(size=9, color=SEVERITY_COLORS["mild"], opacity=0.7),
                name=label,
            ))
            fig.update_xaxes(title_text="Prior survei (0–1)", range=[0, 1])
            fig.update_yaxes(title_text="Intensitas teramati (0–1)", range=[0, 1])
            fig.update_layout(title=f"{label} ({r_text}, n={len(xs)})")
            apply_chart_theme(fig, height=320)
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
        label = (row.get("kelas") or "").lower()
        if "makro" in label:
            try:
                macro_f1 = float(row.get("f1_score") or 0.0)
            except ValueError:
                macro_f1 = None
        elif "tertimbang" in label:
            try:
                weighted_f1 = float(row.get("f1_score") or 0.0)
            except ValueError:
                weighted_f1 = None

    cols = st.columns(4)
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

    img_cols = st.columns(2)
    with img_cols[0]:
        if perf["feature_importance_path"]:
            st.markdown("**Pentingnya Fitur (Feature Importance)**")
            st.image(perf["feature_importance_path"], use_container_width=True)
    with img_cols[1]:
        if perf["decision_tree_path"]:
            st.markdown("**Pohon Keputusan**")
            st.image(perf["decision_tree_path"], use_container_width=True)

    if perf["generated_at"]:
        st.caption(f"Dihasilkan pada: {perf['generated_at']}")
    if summary.get("used_synthetic_data"):
        st.info(
            "Catatan: model dilatih menggunakan data sintetis karena jumlah "
            "rekaman UAT belum mencapai ambang minimum."
        )


def _section_bulk_export(
    users_rows: list[dict],
    sessions_rows: list[dict],
    snapshots_rows: list[dict],
) -> None:
    st.subheader("Ekspor Massal")
    st.caption(
        "Unduh keseluruhan data UAT untuk analisis statistik di luar aplikasi."
    )
    cols = st.columns(3)
    with cols[0]:
        st.download_button(
            label="Semua Pengguna (CSV)",
            data=_csv_bytes(users_rows),
            file_name="research_all_users.csv",
            mime="text/csv",
            key="dl_all_users",
            disabled=not users_rows,
            use_container_width=True,
        )
    with cols[1]:
        st.download_button(
            label="Semua Sesi (CSV)",
            data=_csv_bytes(sessions_rows),
            file_name="research_all_sessions.csv",
            mime="text/csv",
            key="dl_all_sessions",
            disabled=not sessions_rows,
            use_container_width=True,
        )
    with cols[2]:
        st.download_button(
            label="Snapshot CDT (CSV)",
            data=_csv_bytes(snapshots_rows),
            file_name="research_cdt_snapshots.csv",
            mime="text/csv",
            key="dl_all_snapshots",
            disabled=not snapshots_rows,
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def render_researcher_page() -> None:
    """Render the full researcher view (after auth)."""
    if not _ensure_authenticated():
        return

    st.title("Mode Peneliti — Inspeksi UAT")
    st.caption(
        f"Akses berhasil. Waktu server: {fmt_datetime_wib(__import__('datetime').datetime.now(__import__('datetime').timezone.utc))}."
    )

    with get_session() as sess:
        summary = get_cohort_summary(sess)
        users_rows = export_all_users_csv(sess)
        sessions_rows = export_all_sessions_csv(sess)
        snapshots_rows = export_cdt_snapshots_csv(sess)

    tabs = st.tabs([
        "Ringkasan",
        "Peserta",
        "Distribusi",
        "Trajektori",
        "Survei vs. Observasi",
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
        _section_survey_vs_observed(users_rows)
    with tabs[5]:
        _section_model_performance()
    with tabs[6]:
        _section_bulk_export(users_rows, sessions_rows, snapshots_rows)


# When Streamlit auto-discovers this file under ``pages/`` and executes it as
# a script (sidebar navigation), Streamlit's ScriptRunner sets ``__name__`` to
# ``"__main__"``. Plain ``import`` from app.py keeps it as ``pages.researcher``.
if __name__ == "__main__":
    render_researcher_page()
