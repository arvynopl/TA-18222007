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

import plotly.graph_objects as go
import streamlit as st

from config import INITIAL_CAPITAL
from database.connection import get_session, init_db
from database.models import BiasMetric, CognitiveProfile, User
from database.seed import run_seed
from modules.feedback.renderer import render_feedback_page
from modules.simulation.ui import render_simulation_page

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
# Sidebar — navigation + user info
# ---------------------------------------------------------------------------
def _sidebar() -> str:
    """Render the sidebar and return the selected page name."""
    with st.sidebar:
        st.title("📊 CDT Investasi")
        st.caption("Cognitive Digital Twin\nDeteksi Bias Perilaku")

        pages = [
            "Beranda",
            "Simulasi Investasi",
            "Hasil Analisis & Umpan Balik",
            "Profil Kognitif Saya",
        ]

        # Use session state to allow programmatic navigation
        if "current_page" not in st.session_state:
            st.session_state["current_page"] = "Beranda"

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
# Page: Beranda
# ---------------------------------------------------------------------------
def _page_beranda() -> None:
    st.title("Selamat Datang di Sistem CDT Deteksi Bias Investasi")

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
        4. **Umpan Balik* — Kamu menerima penjelasan personal dan rekomendasi perbaikan.
        """
    )

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
        if not alias:
            st.error("Nama tidak boleh kosong.")
            return

        with get_session() as sess:
            user = sess.query(User).filter_by(alias=alias).first()
            if user is None:
                user = User(alias=alias, experience_level=experience)
                sess.add(user)
                sess.flush()
                st.success(f"Akun baru dibuat untuk **{alias}**. Selamat datang!")
            else:
                st.info(f"Selamat datang kembali, **{alias}**!")
            uid = user.id
            exp = user.experience_level

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
    c1.metric("Total Sesi", profile_data["session_count"])
    c2.metric("Indeks Stabilitas", f"{profile_data['stability_index']:.2f}")
    c3.metric("Preferensi Risiko", f"{profile_data['risk_preference']:.2f}")

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
    page = _sidebar()

    if page == "Beranda":
        _page_beranda()
    elif page == "Simulasi Investasi":
        render_simulation_page()
    elif page == "Hasil Analisis & Umpan Balik":
        _page_hasil()
    elif page == "Profil Kognitif Saya":
        _page_profil()


if __name__ == "__main__":
    main()
