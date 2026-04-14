"""
app.py — CDT Bias Detection System — Streamlit multi-page entry point.

Pages (Bahasa Indonesia):
    1. Beranda              — User registration / login
    2. Simulasi Investasi   — 14-round investment simulation
    3. Hasil Analisis & Umpan Balik — Post-session feedback
    4. Profil Kognitif Saya — CDT profile visualisation

Run with:
    streamlit run app.py
"""

import logging
import os
import re

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from sqlalchemy.exc import IntegrityError

from config import INITIAL_CAPITAL, validate_config
from database.connection import get_session, init_db
from database.models import BiasMetric, CdtSnapshot, CognitiveProfile, User
from database.seed import run_seed
from modules.feedback.renderer import render_feedback_page
from modules.simulation.ui import render_simulation_page
from modules.utils.log_config import configure_logging

# CDT_DEBUG=1 enables verbose DEBUG logging to app.log
configure_logging(debug=bool(os.environ.get("CDT_DEBUG")))
logger = logging.getLogger(__name__)

# Validate configuration at startup — raises ValueError immediately if thresholds
# are misconfigured, rather than silently producing wrong severity scores later.
validate_config()

# ---------------------------------------------------------------------------
# App-wide configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CDT — Deteksi Bias Investasi",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# One-time DB init (idempotent)
# ---------------------------------------------------------------------------
@st.cache_resource
def _bootstrap_database():
    """Initialise DB tables and seed reference data on first run."""
    run_seed()


_bootstrap_database()


# ---------------------------------------------------------------------------
# Centralised session state initialisation  (Enhancement 3)
# ---------------------------------------------------------------------------
def _init_session_state() -> None:
    """Ensure all expected session state keys exist with safe defaults."""
    defaults = {
        "current_page": "Informasi & Persetujuan",
        "user_id": None,
        "user_alias": None,
        "experience_level": None,
        "last_session_id": None,
        "consent_given": False,
        "show_survey": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ---------------------------------------------------------------------------
# Sidebar — navigation + user info
# ---------------------------------------------------------------------------
def _sidebar() -> str:
    """Render the sidebar and return the selected page name."""
    with st.sidebar:
        st.title("📊 CDT Investasi")
        st.caption("Cognitive Digital Twin\nDeteksi Bias Perilaku")

        pages = [
            "Informasi & Persetujuan",
            "Beranda",
            "Simulasi Investasi",
            "Hasil Analisis & Umpan Balik",
            "Profil Kognitif Saya",
        ]

        selected = st.radio(
            "Navigasi",
            options=pages,
            index=pages.index(st.session_state["current_page"]),
            key="_nav_radio",
        )
        st.session_state["current_page"] = selected

        st.divider()
        if st.session_state.get("user_alias"):
            st.markdown(f"**Pengguna:** {st.session_state['user_alias']}")
            st.caption(
                f"Tingkat: {st.session_state.get('experience_level', '—').capitalize()}"
            )
        else:
            st.caption("Belum login")

        st.divider()
        st.caption("Thesis ITB • CDT Framework")

    return selected


# ---------------------------------------------------------------------------
# Page: Informasi & Persetujuan
# ---------------------------------------------------------------------------
def _page_consent() -> None:
    """UAT consent and research information page."""
    st.markdown("# 📋 Informasi Penelitian & Persetujuan")
    st.caption("Baca informasi berikut sebelum berpartisipasi dalam simulasi.")

    tab_info, tab_data, tab_consent = st.tabs([
        "ℹ️ Tentang Penelitian",
        "🔒 Data yang Dikumpulkan",
        "✅ Persetujuan",
    ])

    with tab_info:
        st.markdown(
            """
            ## Tentang Penelitian Ini

            Sistem ini dikembangkan sebagai bagian dari penelitian tugas akhir di
            **Institut Teknologi Bandung (ITB)**, Program Studi Sistem dan Teknologi Informasi.
            Penelitian ini bertujuan untuk membangun sebuah *Cognitive Digital Twin* (CDT) yang
            mampu mendeteksi dan memitigasi bias perilaku investor ritel di pasar modal Indonesia.

            ## Apa yang Akan Kamu Lakukan?

            Kamu akan diminta untuk menyelesaikan **1–3 sesi simulasi investasi** menggunakan
            data historis saham IDX. Setiap sesi terdiri dari 14 putaran di mana kamu memutuskan
            untuk membeli, menjual, atau menahan 12 saham IDX pilihan. Setelah setiap sesi, sistem
            akan menganalisis pola keputusanmu dan memberikan umpan balik personal.

            Estimasi waktu per sesi: **15–20 menit**.
            """
        )

    with tab_data:
        st.markdown(
            """
            ## Data yang Dikumpulkan

            Sistem ini mengumpulkan data berikut selama partisipasi:
            - **Keputusan investasi** (beli / jual / tahan) beserta jumlah lembar saham
            - **Waktu respons** untuk setiap keputusan (dalam milidetik)
            - **Alias / nama panggilan** yang kamu masukkan saat login (bukan nama asli)

            **Data tidak dikaitkan dengan identitas asli kamu.** Semua data disimpan secara
            lokal dan hanya digunakan untuk keperluan penelitian akademis.

            ## Kerahasiaan Data

            - Tidak ada data pribadi yang dikumpulkan
            - Data disimpan secara lokal di perangkat penyelenggara penelitian
            - Partisipasi bersifat sukarela dan dapat dihentikan kapan saja
            """
        )

    with tab_consent:
        st.markdown("## Persetujuan Partisipasi")
        st.markdown(
            "Dengan mencentang kotak di bawah, kamu menyatakan bahwa kamu telah membaca "
            "informasi penelitian dan bersedia berpartisipasi secara sukarela."
        )
        st.divider()

        consent = st.checkbox(
            "Saya telah membaca informasi di atas dan **menyetujui** partisipasi dalam penelitian ini.",
            value=st.session_state.get("consent_given", False),
            key="consent_checkbox",
        )

        if consent:
            st.session_state["consent_given"] = True
            st.success(
                "Terima kasih atas persetujuanmu! Silakan lanjutkan ke halaman **Beranda** "
                "untuk login dan memulai simulasi."
            )
            if st.button("Lanjut ke Beranda →", type="primary"):
                st.session_state["current_page"] = "Beranda"
                st.rerun()
        else:
            st.session_state["consent_given"] = False
            st.info(
                "Centang kotak di atas untuk menyetujui partisipasi dan membuka akses ke simulasi."
            )


# ---------------------------------------------------------------------------
# Page: Beranda
# ---------------------------------------------------------------------------
def _page_beranda() -> None:
    st.title("Selamat Datang di Sistem CDT Deteksi Bias Investasi")

    if not st.session_state.get("consent_given"):
        st.warning(
            "Kamu belum memberikan persetujuan partisipasi. "
            "Silakan baca informasi penelitian di halaman **Informasi & Persetujuan** terlebih dahulu."
        )
        if st.button("Ke Halaman Persetujuan →"):
            st.session_state["current_page"] = "Informasi & Persetujuan"
            st.rerun()
        return

    # Session history for logged-in users
    user_id = st.session_state.get("user_id")
    if user_id:
        with get_session() as sess:
            past = (
                sess.query(BiasMetric)
                .filter_by(user_id=user_id)
                .order_by(BiasMetric.computed_at.desc())
                .all()
            )
            session_count = len(past)
            last_date = past[0].computed_at if past else None

        # Prominent CTA at the top
        if st.button("🚀 Mulai Sesi Simulasi Baru", use_container_width=True, type="primary"):
            st.session_state["current_page"] = "Simulasi Investasi"
            st.rerun()

        st.divider()
        st.subheader("Riwayat Sesimu")

        c1, c2 = st.columns(2)
        c1.metric("Total Sesi Selesai", session_count)
        if last_date:
            c2.metric("Sesi Terakhir", last_date.strftime("%d %b %Y %H:%M"))
        else:
            c2.metric("Sesi Terakhir", "—")

        # Progress toward minimum 3 sessions
        min_sessions = 3
        progress_val = min(session_count / min_sessions, 1.0)
        st.progress(progress_val, text=f"{session_count} / {min_sessions} sesi minimum tercapai")

        if session_count == 0:
            st.info("Kamu belum menyelesaikan sesi simulasi. Mulai sekarang!")
        elif session_count < 3:
            st.warning(
                f"Kamu telah menyelesaikan {session_count} dari minimal 3 sesi. "
                f"Selesaikan {3 - session_count} sesi lagi untuk analisis longitudinal yang bermakna."
            )
        else:
            st.success(
                f"Kamu telah menyelesaikan {session_count} sesi — cukup untuk analisis longitudinal. "
                f"Kamu bisa melanjutkan sesi tambahan untuk memperkaya profil kognitifmu."
            )

    with st.expander("ℹ️ Bagaimana sistem ini bekerja?", expanded=not bool(user_id)):
        st.markdown(
            """
            Sistem ini dirancang untuk membantu investor ritel memahami pola pengambilan
            keputusan mereka melalui **simulasi investasi berbasis data historis saham IDX**.

            **4 Langkah Proses:**

            1. **Simulasi** — Kamu akan memainkan 14 putaran investasi menggunakan data
               historis 12 saham IDX nyata.
            2. **Analisis** — Setelah sesi selesai, sistem menghitung tiga metrik bias kognitif:
               - *Efek Disposisi* — Kecenderungan menjual saham untung terlalu cepat
               - *Overconfidence* — Terlalu sering trading dengan hasil kurang optimal
               - *Loss Aversion* — Menahan saham rugi terlalu lama
            3. **Profil Kognitif** — Profilmu diperbarui setelah setiap sesi menggunakan
               model *Cognitive Digital Twin* (CDT) berbasis EMA. Sistem juga mendeteksi
               **Preferensi Risiko** kamu (Konservatif / Moderat / Agresif) berdasarkan
               volatilitas saham yang kamu pilih — tanpa kamu harus mengisi kuesioner.
            4. **Umpan Balik** — Kamu menerima penjelasan personal dan rekomendasi perbaikan.
            """
        )

    if not user_id:
        st.divider()
        st.subheader("Login / Daftar")

        with st.form("login_form"):
            alias = st.text_input(
                "Nama / Alias",
                placeholder="Masukkan nama atau alias kamu",
                max_chars=64,
            )
            experience = st.selectbox(
                "Tingkat Pengalaman Investasi",
                options=["beginner", "intermediate", "advanced"],
                format_func=lambda x: {"beginner": "Pemula", "intermediate": "Menengah", "advanced": "Berpengalaman"}[x],
            )
            st.caption(
                "**Pemula:** Belum pernah atau jarang berinvestasi saham. "
                "**Menengah:** Sudah aktif berinvestasi 1–3 tahun. "
                "**Berpengalaman:** Investor aktif >3 tahun atau memiliki latar belakang keuangan formal."
            )
            submitted = st.form_submit_button("Masuk →", use_container_width=True, type="primary")

        if submitted:
            alias = alias.strip()
            if not alias or len(alias) < 2:
                st.error("Nama harus minimal 2 karakter.")
                return
            if not re.match(r'^[a-zA-Z0-9 ]+$', alias):
                st.error("Nama hanya boleh mengandung huruf, angka, dan spasi.")
                return

            try:
                with get_session() as sess:
                    user = sess.query(User).filter_by(alias=alias).first()
                    if user is None:
                        user = User(alias=alias, experience_level=experience)
                        sess.add(user)
                        sess.flush()
                        logger.info("New user created: alias=%r", alias)
                        st.success(f"Akun baru dibuat untuk **{alias}**. Selamat datang!")
                    else:
                        logger.info("Existing user login: alias=%r id=%d", alias, user.id)
                        st.info(f"Selamat datang kembali, **{alias}**!")
                    uid = user.id
                    exp = user.experience_level
            except IntegrityError:
                st.error("Alias sudah digunakan oleh akun lain. Silakan pilih alias berbeda.")
                return

            st.session_state["user_id"] = uid
            st.session_state["user_alias"] = alias
            st.session_state["experience_level"] = exp

            # Persist consent record for audit trail
            if st.session_state.get("consent_given"):
                from database.models import ConsentLog
                try:
                    with get_session() as consent_sess:
                        existing = consent_sess.query(ConsentLog).filter_by(
                            user_id=uid, consent_given=True
                        ).first()
                        if not existing:
                            consent_sess.add(ConsentLog(
                                user_id=uid,
                                consent_given=True,
                                consent_text="Saya telah membaca informasi penelitian dan menyetujui partisipasi.",
                            ))
                except Exception:
                    logger.warning("Failed to persist consent log for user %d", uid)

            # Check if user already completed survey
            from database.models import UserSurvey
            try:
                with get_session() as check_sess:
                    has_survey = check_sess.query(UserSurvey).filter_by(user_id=uid).first() is not None
            except Exception:
                has_survey = True  # fail-safe: skip survey on error

            if not has_survey:
                st.session_state["show_survey"] = True
                st.rerun()
            else:
                st.session_state["current_page"] = "Simulasi Investasi"
                st.rerun()

        # --- Optional Risk Preference Survey ---
        if st.session_state.get("show_survey") and st.session_state.get("user_id"):
            st.divider()
            with st.expander("📋 Isi Survei Preferensi Risiko (Opsional)", expanded=True):
                st.caption(
                    "Survei ini membantu peneliti membandingkan preferensi yang Anda "
                    "nyatakan dengan perilaku aktual di simulasi. Data tidak memengaruhi "
                    "simulasi atau skor Anda. Anda dapat melewati survei ini."
                )

                LIKERT_LABELS = {
                    1: "1 — Sangat Tidak Setuju",
                    2: "2 — Tidak Setuju",
                    3: "3 — Netral",
                    4: "4 — Setuju",
                    5: "5 — Sangat Setuju",
                }

                with st.form("survey_form"):
                    q1 = st.select_slider(
                        "Saya bersedia mengambil risiko tinggi demi potensi keuntungan besar.",
                        options=[1, 2, 3, 4, 5],
                        value=3,
                        format_func=lambda x: LIKERT_LABELS[x],
                    )
                    q2 = st.select_slider(
                        "Saya merasa sangat terganggu ketika investasi saya mengalami kerugian sementara.",
                        options=[1, 2, 3, 4, 5],
                        value=3,
                        format_func=lambda x: LIKERT_LABELS[x],
                    )
                    q3 = st.select_slider(
                        "Saya merasa perlu sering melakukan transaksi untuk mendapatkan hasil optimal.",
                        options=[1, 2, 3, 4, 5],
                        value=3,
                        format_func=lambda x: LIKERT_LABELS[x],
                    )
                    q4 = st.select_slider(
                        "Ketika harga saham turun, saya cenderung menahan saham tersebut daripada menjualnya.",
                        options=[1, 2, 3, 4, 5],
                        value=3,
                        format_func=lambda x: LIKERT_LABELS[x],
                    )

                    col_submit, col_skip = st.columns(2)
                    with col_submit:
                        survey_submitted = st.form_submit_button(
                            "Simpan Survei", use_container_width=True, type="primary"
                        )
                    with col_skip:
                        survey_skipped = st.form_submit_button(
                            "Lewati →", use_container_width=True
                        )

                if survey_submitted:
                    uid = st.session_state["user_id"]
                    try:
                        from database.models import UserSurvey
                        with get_session() as survey_sess:
                            survey_sess.add(UserSurvey(
                                user_id=uid,
                                q_risk_tolerance=q1,
                                q_loss_sensitivity=q2,
                                q_trading_frequency=q3,
                                q_holding_behavior=q4,
                            ))
                        st.success("Survei berhasil disimpan. Terima kasih!")
                    except Exception:
                        logger.warning("Failed to save survey for user %d", uid)

                    st.session_state["show_survey"] = False
                    st.session_state["current_page"] = "Simulasi Investasi"
                    st.rerun()

                if survey_skipped:
                    st.session_state["show_survey"] = False
                    st.session_state["current_page"] = "Simulasi Investasi"
                    st.rerun()


# ---------------------------------------------------------------------------
# Page: Profil Kognitif Saya
# ---------------------------------------------------------------------------
def _page_profil() -> None:
    st.title("Profil Kognitif Saya")

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.warning("Silakan login terlebih dahulu.")
        return

    with get_session() as sess:
        profile = sess.query(CognitiveProfile).filter_by(user_id=user_id).first()
        past_metrics = (
            sess.query(BiasMetric)
            .filter_by(user_id=user_id)
            .order_by(BiasMetric.computed_at)
            .all()
        )
        # Serialise into plain dicts before session closes
        metrics_data = [
            {
                "session_num": i + 1,
                "ocs": m.overconfidence_score or 0.0,
                "dei": abs(m.disposition_dei or 0.0),
                "lai_norm": min((m.loss_aversion_index or 0.0) / 3.0, 1.0),
                "computed_at": m.computed_at,
            }
            for i, m in enumerate(past_metrics)
        ]
        # Serialise CdtSnapshot history (used by the interaction heatmap)
        snapshots_data = [
            {
                "session_number": s.session_number,
                "cdt_overconfidence": s.cdt_overconfidence,
                "cdt_disposition": s.cdt_disposition,
            }
            for s in (
                sess.query(CdtSnapshot)
                .filter_by(user_id=user_id)
                .order_by(CdtSnapshot.session_number)
                .all()
            )
        ]
        profile_data = None
        anomaly_data = None
        if profile:
            profile_data = {
                "bias_vector": dict(profile.bias_intensity_vector),
                "risk_preference": profile.risk_preference,
                "stability_index": profile.stability_index,
                "session_count": profile.session_count,
                "last_updated_at": profile.last_updated_at,
                "interaction_scores": profile.interaction_scores,
            }
            # Fetch ML anomaly flags (requires sklearn; silently degrades)
            from modules.cdt.ml_validator import compute_anomaly_flags
            anomaly_data = compute_anomaly_flags(sess, user_id)

    if profile_data is None:
        st.info("Selesaikan setidaknya satu sesi simulasi untuk melihat profil kognitifmu.")
        return

    from modules.utils.ui_helpers import (
        apply_chart_theme, build_radar_chart, BIAS_NAMES, SEVERITY_COLORS,
    )

    # --- Summary metrics hero strip ---
    st.markdown("### 🧠 Profil Kognitif Digital Twin")
    st.caption("Representasi adaptif pola pengambilan keputusan investasimu, diperbarui setelah setiap sesi.")

    c1, c2, c3 = st.columns(3)
    rp = profile_data["risk_preference"]
    rp_label = (
        "Agresif" if rp >= 0.6
        else "Moderat" if rp >= 0.3
        else "Konservatif"
    )
    si = profile_data["stability_index"]
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

    with st.expander("Apa itu Preferensi Risiko?"):
        st.markdown(
            """
            **Preferensi Risiko** mencerminkan seberapa sering kamu memilih saham bervolatilitas
            tinggi (misalnya ANTM, GOTO) dibandingkan saham konservatif (misalnya BBCA, TLKM).

            | Skor | Kategori | Arti |
            |------|----------|------|
            | 0.6 – 1.0 | Agresif | Sering memilih saham berisiko tinggi |
            | 0.3 – 0.6 | Moderat | Campuran saham berisiko sedang |
            | 0.0 – 0.3 | Konservatif | Cenderung memilih saham stabil |

            Nilai ini diperbarui menggunakan model *Exponential Moving Average* (EMA)
            setelah setiap sesi, sehingga mencerminkan tren terbaru perilakumu.
            """
        )

    st.divider()

    # --- Radar chart (shared themed component) ---
    bv = profile_data["bias_vector"]
    radar = build_radar_chart(bv, "Vektor Intensitas Bias (CDT)")
    st.plotly_chart(radar, use_container_width=True)

    # --- Session history line chart ---
    if len(metrics_data) >= 2:
        st.subheader("📊 Riwayat Metrik per Sesi")
        sessions = [f"Sesi {d['session_num']}" for d in metrics_data]

        line_fig = go.Figure()
        line_fig.add_trace(go.Scatter(
            x=sessions, y=[d["ocs"] for d in metrics_data],
            mode="lines+markers", name="Overconfidence (OCS)",
            line=dict(color=SEVERITY_COLORS["mild"], width=2),
            marker=dict(size=8),
        ))
        line_fig.add_trace(go.Scatter(
            x=sessions, y=[d["dei"] for d in metrics_data],
            mode="lines+markers", name="Efek Disposisi |DEI|",
            line=dict(color=SEVERITY_COLORS["moderate"], width=2),
            marker=dict(size=8),
        ))
        line_fig.add_trace(go.Scatter(
            x=sessions, y=[d["lai_norm"] for d in metrics_data],
            mode="lines+markers", name="Loss Aversion (norm)",
            line=dict(color=SEVERITY_COLORS["severe"], width=2),
            marker=dict(size=8),
        ))
        line_fig.update_yaxes(title_text="Intensitas Bias (0–1)", range=[0, 1])
        apply_chart_theme(line_fig, height=380)
        st.plotly_chart(line_fig, use_container_width=True)

    # --- Cross-Bias Interaction Scores ---
    interaction = profile_data.get("interaction_scores")
    if interaction:
        st.subheader("🔗 Interaksi Antar Bias")
        st.caption(
            "Korelasi Pearson antara bias-biasmu. Nilai mendekati +1 berarti dua bias "
            "sering muncul bersamaan; mendekati -1 berarti saling berlawanan."
        )

        def _fmt_corr(v) -> str:
            if v is None:
                return "—"
            bar = "█" * int(abs(v) * 10)
            direction = "+" if v >= 0 else "−"
            return f"{direction}{abs(v):.2f} {bar}"

        ic1, ic2, ic3 = st.columns(3)
        ic1.metric(
            "OCS ↔ |DEI|",
            _fmt_corr(interaction.get("ocs_dei")),
            help="Korelasi antara Overconfidence dan Efek Disposisi",
            delta=" ", delta_color="off",
        )
        ic2.metric(
            "OCS ↔ LAI",
            _fmt_corr(interaction.get("ocs_lai")),
            help="Korelasi antara Overconfidence dan Loss Aversion",
            delta=" ", delta_color="off",
        )
        ic3.metric(
            "│DEI│ ↔ LAI",
            _fmt_corr(interaction.get("dei_lai")),
            help="Korelasi antara Efek Disposisi dan Loss Aversion",
            delta=" ", delta_color="off",
        )

        # Narrative interpretation for the strongest pair
        valid_pairs = {k: v for k, v in interaction.items() if v is not None}
        if valid_pairs:
            strongest_pair = max(valid_pairs, key=lambda k: abs(valid_pairs[k]))
            val = valid_pairs[strongest_pair]
            pair_names = {
                "ocs_dei": "Overconfidence dan Efek Disposisi",
                "ocs_lai": "Overconfidence dan Loss Aversion",
                "dei_lai": "Efek Disposisi dan Loss Aversion",
            }
            if abs(val) >= 0.6:
                direction = "cenderung muncul bersamaan" if val > 0 else "saling berlawanan"
                st.info(
                    f"💡 **{pair_names[strongest_pair]}** {direction} (r={val:+.2f}). "
                    f"Ini menunjukkan pola perilaku yang saling terkait pada profilmu."
                )

    # --- Peta Interaksi Bias (DEI × OCS heatmap) ---
    st.subheader("🗺️ Peta Interaksi Bias")
    st.caption(
        "Visualisasi posisi biasmu dalam ruang interaksi DEI × OCS. "
        "Zona merah menandakan risiko tinggi akibat kombinasi Overconfidence dan Efek Disposisi."
    )
    if len(snapshots_data) < 2:
        st.info("Selesaikan minimal 2 sesi untuk melihat peta interaksi Anda.")
    else:
        from modules.cdt.interaction import build_interaction_heatmap_data

        hm_data = build_interaction_heatmap_data(snapshots_data)

        hm_fig = go.Figure()

        # Background: joint severity heatmap (blue=low → orange=moderate → red=high)
        hm_fig.add_trace(go.Heatmap(
            x=hm_data["x"],
            y=hm_data["y"],
            z=hm_data["z"],
            colorscale=[
                [0.0, "#1a3a5c"],   # deep blue  – low risk
                [0.5, "#F5A623"],   # amber      – moderate risk
                [1.0, "#E8553A"],   # red-orange – high risk
            ],
            zmin=0.0,
            zmax=1.0,
            showscale=True,
            colorbar=dict(
                title=dict(text="Tingkat<br>Interaksi", font=dict(color="#E0E0E0", size=11)),
                tickfont=dict(color="#E0E0E0"),
                thickness=14,
            ),
            hovertemplate=(
                "DEI: %{x:.2f}<br>OCS: %{y:.2f}<br>Interaksi: %{z:.2f}"
                "<extra></extra>"
            ),
        ))

        # User trajectory: numbered scatter points
        hm_fig.add_trace(go.Scatter(
            x=hm_data["scatter_x"],
            y=hm_data["scatter_y"],
            mode="markers+text",
            marker=dict(
                size=16,
                color="white",
                line=dict(color="#E8553A", width=2),
                symbol="circle",
            ),
            text=hm_data["scatter_labels"],
            textposition="top center",
            textfont=dict(color="white", size=11, family="sans-serif"),
            hovertext=hm_data["scatter_text"],
            hoverinfo="text",
            name="Sesi Anda",
        ))

        hm_fig.update_xaxes(
            title_text="Skor DEI (Efek Disposisi)",
            range=[0, 1],
            gridcolor="#2a3a4a",
            zeroline=False,
        )
        hm_fig.update_yaxes(
            title_text="Skor OCS (Overconfidence)",
            range=[0, 1],
            gridcolor="#2a3a4a",
            zeroline=False,
        )
        apply_chart_theme(hm_fig, height=460)
        # Override legend placement — single-trace heatmap doesn't need a legend
        hm_fig.update_layout(showlegend=False)
        st.plotly_chart(hm_fig, use_container_width=True)
        st.caption(
            "Titik merah menunjukkan pola perdagangan berisiko tinggi "
            "(Overconfident + Disposition Effect)"
        )

    # --- ML Anomaly Detection Panel ---
    if anomaly_data:
        st.subheader("🤖 Deteksi Sesi Anomali (ML)")
        n = anomaly_data["n_sessions"]
        n_anomaly = sum(anomaly_data["is_anomaly"])
        st.caption(
            f"Isolation Forest dijalankan pada {n} sesi. "
            f"Sesi yang strukturnya menyimpang dari baseline perilakumu ditandai sebagai anomali."
        )

        if n_anomaly == 0:
            st.success(
                "✅ Tidak ada sesi anomali terdeteksi — pola biasmu konsisten di semua sesi."
            )
        else:
            st.warning(
                f"⚠️ {n_anomaly} dari {n} sesi menunjukkan profil bias yang tidak biasa. "
                f"Ini bisa berarti kamu bereksperimen dengan strategi berbeda, "
                f"atau kondisi pasar mendorong perilaku yang tidak khas."
            )

        import pandas as pd
        rows = []
        for i, (sid, score, flag) in enumerate(
            zip(
                anomaly_data["session_ids"],
                anomaly_data["anomaly_scores"],
                anomaly_data["is_anomaly"],
            )
        ):
            rows.append({
                "Sesi": f"#{i + 1}",
                "Anomali": "⚠️ Ya" if flag else "✅ Normal",
                "Skor": f"{score:.3f}",
                "ID (8 digit)": sid[:8],
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    elif profile_data["session_count"] > 0:
        from modules.cdt.ml_validator import _MIN_SESSIONS_FOR_ML
        remaining = _MIN_SESSIONS_FOR_ML - profile_data["session_count"]
        if remaining > 0:
            st.caption(
                f"🤖 Deteksi anomali ML tersedia setelah {_MIN_SESSIONS_FOR_ML} sesi "
                f"(butuh {remaining} sesi lagi)."
            )

    # --- Insight section ---
    st.subheader("💡 Insight")
    if bv:
        max_bias = max(bv, key=bv.get)
        max_val = bv[max_bias]
        bias_name = BIAS_NAMES.get(max_bias, max_bias)

        if max_val < 0.15:
            st.success(
                "Profil biasmu menunjukkan pola pengambilan keputusan yang sehat secara keseluruhan. "
                "Terus pertahankan pendekatan analitis dalam setiap keputusan investasi."
            )
        elif max_val < 0.4:
            st.info(
                f"Kecenderungan tertinggimu saat ini adalah **{bias_name}** "
                f"(intensitas: {max_val:.2f}). Ini masih dalam batas ringan, namun perlu "
                f"dipantau agar tidak meningkat di sesi-sesi mendatang."
            )
        else:
            st.warning(
                f"Perhatian: **{bias_name}** menunjukkan intensitas {max_val:.2f}. "
                f"Fokuslah pada rekomendasi yang diberikan di halaman Hasil Analisis "
                f"untuk mengurangi kecenderungan ini."
            )

        if profile_data["session_count"] >= 3:
            if si > 0.8:
                st.caption(
                    "📌 Pola biasmu sangat konsisten antar sesi — baik jika kamu sudah di zona sehat, "
                    "tapi perlu perhatian jika bias masih tinggi."
                )
            elif si < 0.4:
                st.caption(
                    "📌 Pola biasmu cukup fluktuatif antar sesi — ini bisa berarti kamu sedang "
                    "beradaptasi dan belajar dari umpan balik."
                )

    if profile_data["last_updated_at"]:
        st.caption(f"Terakhir diperbarui: {profile_data['last_updated_at'].strftime('%d %b %Y %H:%M')}")

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

    # --- Data Export Section ---
    st.divider()
    st.subheader("Ekspor Data")
    st.caption("Unduh data sesi untuk evaluasi dan analisis lebih lanjut.")

    import io
    import csv
    from modules.utils.export import export_user_history_csv

    with get_session() as export_sess:
        history_rows = export_user_history_csv(export_sess, user_id)

    if history_rows:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=history_rows[0].keys())
        writer.writeheader()
        writer.writerows(history_rows)
        csv_data = output.getvalue()

        st.download_button(
            label="📥 Unduh Riwayat Sesi (CSV)",
            data=csv_data,
            file_name=f"cdt_history_{st.session_state.get('user_alias', 'user')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("Belum ada data sesi untuk diekspor.")


# ---------------------------------------------------------------------------
# Page: Hasil Analisis
# ---------------------------------------------------------------------------
def _page_hasil() -> None:
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.warning("Silakan login terlebih dahulu.")
        return

    session_id = st.session_state.get("last_session_id")
    if not session_id:
        st.info("Selesaikan sesi simulasi terlebih dahulu untuk melihat hasil analisis.")
        return

    render_feedback_page(user_id=user_id, session_id=session_id)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def main() -> None:
    _init_session_state()
    from modules.utils.ui_helpers import inject_custom_css
    inject_custom_css()
    page = _sidebar()

    if page == "Informasi & Persetujuan":
        _page_consent()
    elif page == "Beranda":
        _page_beranda()
    elif page == "Simulasi Investasi":
        if not st.session_state.get("consent_given"):
            st.warning("Silakan setujui partisipasi penelitian di halaman **Informasi & Persetujuan** terlebih dahulu.")
        else:
            render_simulation_page()
    elif page == "Hasil Analisis & Umpan Balik":
        _page_hasil()
    elif page == "Profil Kognitif Saya":
        _page_profil()


if __name__ == "__main__":
    main()
