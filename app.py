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
from sqlalchemy.exc import IntegrityError

from config import INITIAL_CAPITAL
from database.connection import get_session, init_db
from database.models import BiasMetric, CognitiveProfile, User
from database.seed import run_seed
from modules.feedback.renderer import render_feedback_page
from modules.simulation.ui import render_simulation_page
from modules.utils.log_config import configure_logging

# CDT_DEBUG=1 enables verbose DEBUG logging to app.log
configure_logging(debug=bool(os.environ.get("CDT_DEBUG")))
logger = logging.getLogger(__name__)

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
    st.title("Informasi Penelitian & Persetujuan Partisipasi")

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
        untuk membeli, menjual, atau menahan 6 saham IDX pilihan. Setelah setiap sesi, sistem
        akan menganalisis pola keputusanmu dan memberikan umpan balik personal.

        Estimasi waktu per sesi: **15–20 menit**.

        ## Data yang Dikumpulkan

        Sistem ini mengumpulkan data berikut selama partisipasi:
        - **Keputusan investasi** (beli / jual / tahan) beserta jumlah lembar saham
        - **Waktu respons** untuk setiap keputusan (dalam milidetik)
        - **Alias / nama panggilan** yang kamu masukkan saat login (bukan nama asli)

        **Data tidak dikaitkan dengan identitas asli kamu.** Semua data disimpan secara
        lokal dan hanya digunakan untuk keperluan penelitian akademis.
        """
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

    st.markdown(
        """
        Sistem ini dirancang untuk membantu investor ritel memahami pola pengambilan
        keputusan mereka melalui **simulasi investasi berbasis data historis saham IDX**.

        ### Cara Kerja
        1. **Simulasi** — Kamu akan memainkan 14 putaran investasi menggunakan data
           historis 6 saham IDX nyata.
        2. **Analisis** — Setelah sesi selesai, sistem menghitung tiga metrik bias kognitif:
           - *Efek Disposisi* — Kecenderungan menjual saham untung terlalu cepat
           - *Overconfidence* — Terlalu sering trading dengan hasil kurang optimal
           - *Loss Aversion* — Menahan saham rugi terlalu lama
        3. **Profil Kognitif** — Profilmu diperbarui setelah setiap sesi menggunakan
           model *Cognitive Digital Twin* (CDT) berbasis EMA.
        4. **Umpan Balik** — Kamu menerima penjelasan personal dan rekomendasi perbaikan.
        """
    )

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

        st.divider()
        st.subheader("Riwayat Sesimu")
        c1, c2 = st.columns(2)
        c1.metric("Total Sesi Selesai", session_count)
        if last_date:
            c2.metric("Sesi Terakhir", last_date.strftime("%d %b %Y %H:%M"))
        else:
            c2.metric("Sesi Terakhir", "—")
        if session_count == 0:
            st.info("Kamu belum menyelesaikan sesi simulasi. Mulai sekarang!")

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
        profile_data = None
        if profile:
            profile_data = {
                "bias_vector": dict(profile.bias_intensity_vector),
                "risk_preference": profile.risk_preference,
                "stability_index": profile.stability_index,
                "session_count": profile.session_count,
                "last_updated_at": profile.last_updated_at,
            }

    if profile_data is None:
        st.info("Selesaikan setidaknya satu sesi simulasi untuk melihat profil kognitifmu.")
        return

    # --- Summary metrics ---
    c1, c2, c3 = st.columns(3)
    rp = profile_data["risk_preference"]
    rp_label = (
        "Agresif" if rp >= 0.6
        else "Moderat" if rp >= 0.3
        else "Konservatif"
    )
    c1.metric("Total Sesi", profile_data["session_count"])
    c2.metric("Indeks Stabilitas", f"{profile_data['stability_index']:.2f}")
    c3.metric("Preferensi Risiko", f"{rp:.2f}", delta=rp_label, delta_color="off")

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

    # --- Radar chart ---
    bv = profile_data["bias_vector"]
    categories = ["Overconfidence", "Efek Disposisi", "Loss Aversion"]
    values = [
        bv.get("overconfidence", 0.0),
        bv.get("disposition", 0.0),
        bv.get("loss_aversion", 0.0),
    ]
    # Close the polygon
    values_closed = values + [values[0]]
    categories_closed = categories + [categories[0]]

    radar = go.Figure(go.Scatterpolar(
        r=values_closed,
        theta=categories_closed,
        fill="toself",
        fillcolor="rgba(31, 119, 180, 0.25)",
        line=dict(color="rgba(31, 119, 180, 0.8)", width=2),
        name="Intensitas Bias",
    ))
    radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        showlegend=False,
        title="Vektor Intensitas Bias (CDT)",
        height=400,
    )
    st.plotly_chart(radar, use_container_width=True)

    # --- Session history line chart ---
    if len(metrics_data) >= 2:
        st.subheader("Riwayat Metrik per Sesi")
        sessions = [f"Sesi {d['session_num']}" for d in metrics_data]

        line_fig = go.Figure()
        line_fig.add_trace(go.Scatter(
            x=sessions, y=[d["ocs"] for d in metrics_data],
            mode="lines+markers", name="Overconfidence (OCS)",
            line=dict(color="#e74c3c"),
        ))
        line_fig.add_trace(go.Scatter(
            x=sessions, y=[d["dei"] for d in metrics_data],
            mode="lines+markers", name="Efek Disposisi |DEI|",
            line=dict(color="#f39c12"),
        ))
        line_fig.add_trace(go.Scatter(
            x=sessions, y=[d["lai_norm"] for d in metrics_data],
            mode="lines+markers", name="Loss Aversion (LAI/3)",
            line=dict(color="#9b59b6"),
        ))
        line_fig.update_layout(
            yaxis=dict(range=[0, 1], title="Intensitas (0–1)"),
            height=350,
            legend=dict(orientation="h", y=-0.2),
        )
        st.plotly_chart(line_fig, use_container_width=True)

    if profile_data["last_updated_at"]:
        st.caption(f"Terakhir diperbarui: {profile_data['last_updated_at'].strftime('%d %b %Y %H:%M')}")


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
