"""
app.py — CDT Bias Detection System (v6). Streamlit multi-page entry point.

Pages (Bahasa Indonesia):
    1. Beranda                         — Login / Registrasi
    2. Simulasi Investasi              — 14-round investment simulation
    3. Hasil Analisis & Umpan Balik    — Post-session feedback
    4. Profil Kognitif Saya            — CDT profile visualisation

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import logging
import os

import plotly.graph_objects as go
import streamlit as st

from config import INITIAL_CAPITAL, validate_config
from database.connection import get_session, init_db
from database.models import (
    BiasMetric, CdtSnapshot, CognitiveProfile, OnboardingSurvey, User, UserProfile,
)
from database.seed import run_seed
from modules.auth import (
    AuthError, DuplicateUsernameError, InvalidCredentialsError,
    RateLimitedError, WeakPasswordError,
    authenticate, register_user, user_exists,
)
from modules.feedback.renderer import render_feedback_page
from modules.simulation.ui import render_simulation_page
from modules.utils.log_config import configure_logging
from modules.utils.ui_helpers import (
    NAV_ITEMS, fmt_datetime_wib, inject_custom_css,
    render_mobile_banner, render_top_nav,
)

# CDT_DEBUG=1 enables verbose DEBUG logging to app.log
configure_logging(debug=bool(os.environ.get("CDT_DEBUG")))
logger = logging.getLogger(__name__)

# Startup configuration validation.
validate_config()

# ---------------------------------------------------------------------------
# App-wide configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Kenali Pola Investasi Anda — CDT",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# Streamlit Cloud safety guard
# ---------------------------------------------------------------------------
# On Streamlit Community Cloud the container filesystem is ephemeral. If
# CDT_DATABASE_URL is unset the app would silently fall back to a local
# SQLite file and lose every write on the next redeploy. Refuse to start
# in that scenario rather than corrupting UAT data.
def _looks_like_streamlit_cloud() -> bool:
    if os.environ.get("STREAMLIT_RUNTIME_ENV") == "cloud":
        return True
    if os.environ.get("STREAMLIT_SHARING_MODE"):
        return True
    if os.path.exists("/mount/src"):  # Streamlit Cloud working directory
        return True
    hostname = os.environ.get("HOSTNAME", "")
    return "streamlit" in hostname.lower()


if _looks_like_streamlit_cloud() and not os.environ.get("CDT_DATABASE_URL"):
    st.error(
        "**Konfigurasi belum lengkap.** Variabel `CDT_DATABASE_URL` belum "
        "diatur pada Streamlit Cloud Secrets. Aplikasi dihentikan untuk "
        "mencegah kehilangan data: file SQLite lokal pada Streamlit Cloud "
        "akan terhapus setiap kali container di-redeploy.\n\n"
        "**Cara memperbaiki:** buka *App settings → Secrets* lalu tambahkan:\n\n"
        "```toml\n"
        'CDT_DATABASE_URL = "postgresql://<user>:<pass>@<host>.neon.tech/<db>?sslmode=require"\n'
        "```\n\n"
        "Lihat `README_DEPLOY.md` untuk panduan lengkap."
    )
    logger.error("Refusing to start on Streamlit Cloud without CDT_DATABASE_URL set.")
    st.stop()


# ---------------------------------------------------------------------------
# One-time DB init (idempotent)
# ---------------------------------------------------------------------------
@st.cache_resource
def _bootstrap_database():
    run_seed()


_bootstrap_database()


# ---------------------------------------------------------------------------
# Session state bootstrap
# ---------------------------------------------------------------------------
def _init_session_state() -> None:
    defaults = {
        "current_page": "Beranda",
        "user_id": None,
        "user_alias": None,
        "experience_level": None,
        "last_session_id": None,
        "auth_stage": "username",   # "username" | "login" | "register"
        "auth_username": "",
        "onboarding_shown": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ---------------------------------------------------------------------------
# Top navigation wrapper
# ---------------------------------------------------------------------------
def _render_header() -> None:
    user_logged_in = bool(st.session_state.get("user_id"))
    has_sessions = False
    if user_logged_in:
        with get_session() as sess:
            has_sessions = (
                sess.query(BiasMetric)
                .filter_by(user_id=st.session_state["user_id"])
                .first()
                is not None
            )

    enabled_map = {
        "Beranda": True,
        "Simulasi Investasi": user_logged_in,
        "Hasil Analisis & Umpan Balik": has_sessions,
        "Profil Kognitif Saya": has_sessions,
    }

    current = st.session_state["current_page"]

    title_col, user_col = st.columns([5, 1])
    with title_col:
        st.markdown("### Kenali Pola Investasi Anda")
        st.caption(
            "Simulasi trading untuk memetakan bias pengambilan keputusan Anda, "
            "ditenagai *Cognitive Digital Twin* (CDT)."
        )
    with user_col:
        if st.session_state.get("user_alias"):
            alias = st.session_state["user_alias"]
            # Identity cluster: logout button and username on the same horizontal level.
            # CSS flex row — button on the left, username label on the right.
            # The button is rendered via st.button (interactive); the username
            # label sits alongside it via a negative-margin markdown trick.
            btn_col, name_col = st.columns([1, 1])
            with btn_col:
                if st.button("Keluar", key="cdt_logout"):
                    _logout()
                    st.rerun()
            with name_col:
                st.markdown(
                    f"<div style='padding-top:8px; font-size:13px; color:#5F6368;'>"
                    f"Pengguna: <b style='color:#1C1E21;'>{alias}</b></div>",
                    unsafe_allow_html=True,
                )

    render_mobile_banner()

    clicked = render_top_nav(current, enabled_map)
    if clicked != current:
        st.session_state["current_page"] = clicked
        st.rerun()


def _logout() -> None:
    for key in [
        "user_id", "user_alias", "experience_level",
        "auth_stage", "auth_username", "last_session_id", "onboarding_shown",
    ]:
        st.session_state.pop(key, None)
    for key in list(st.session_state.keys()):
        if key.startswith("sim_"):
            st.session_state.pop(key, None)
    st.session_state["current_page"] = "Beranda"
    st.session_state["auth_stage"] = "username"
    st.session_state["auth_username"] = ""


# ---------------------------------------------------------------------------
# Page: Beranda / Auth
# ---------------------------------------------------------------------------
_LIKERT_LABELS = {
    1: "1 — Sangat Tidak Setuju",
    2: "2 — Tidak Setuju",
    3: "3 — Netral",
    4: "4 — Setuju",
    5: "5 — Sangat Setuju",
}

# 9 onboarding items — 3 per bias (DEI, OCS, LAI) — aligned with Odean 1998,
# Barber & Odean 2000, Kahneman & Tversky 1979. Ordered DEI → OCS → LAI.
_ONBOARDING_ITEMS: list[tuple[str, str]] = [
    ("dei_q1", "Saya cenderung menjual saham saat sudah untung, "
               "walaupun mungkin masih bisa naik."),
    ("dei_q2", "Saya sering menahan saham yang sedang rugi karena "
               "yakin harganya akan pulih."),
    ("dei_q3", "Saya merasa lega setelah merealisasikan keuntungan, "
               "bahkan yang kecil."),
    ("ocs_q1", "Saya yakin keputusan investasi saya umumnya lebih baik "
               "daripada rata-rata investor lain."),
    ("ocs_q2", "Saya merasa perlu sering melakukan transaksi untuk memperoleh "
               "hasil yang optimal."),
    ("ocs_q3", "Saya percaya kemampuan saya membaca pergerakan pasar "
               "jangka pendek cukup tajam."),
    ("lai_q1", "Saya merasa sangat terganggu ketika portofolio saya "
               "mengalami kerugian sementara."),
    ("lai_q2", "Rasa sakit dari kerugian terasa jauh lebih kuat "
               "dibandingkan kesenangan dari keuntungan setara."),
    ("lai_q3", "Saya cenderung menunda menjual saham yang rugi karena "
               "takut mengunci kerugian."),
]


def _page_beranda() -> None:
    user_id = st.session_state.get("user_id")

    if user_id:
        _render_beranda_logged_in(user_id)
        return

    _render_auth_flow()


def _render_beranda_logged_in(user_id: int) -> None:
    with get_session() as sess:
        past = (
            sess.query(BiasMetric)
            .filter_by(user_id=user_id)
            .order_by(BiasMetric.computed_at.desc())
            .all()
        )
        session_count = len(past)
        last_date = past[0].computed_at if past else None

    if st.button("Mulai Sesi Simulasi Baru", use_container_width=True, type="primary"):
        st.session_state["current_page"] = "Simulasi Investasi"
        st.rerun()

    st.divider()
    st.subheader("Riwayat Sesi Anda")

    c1, c2 = st.columns(2)
    c1.metric("Total Sesi Selesai", session_count)
    c2.metric(
        "Sesi Terakhir",
        fmt_datetime_wib(last_date) if last_date else "—",
    )

    min_sessions = 3
    progress_val = min(session_count / min_sessions, 1.0)
    st.progress(progress_val, text=f"{session_count} / {min_sessions} sesi minimum tercapai")

    if session_count == 0:
        st.info("Anda belum menyelesaikan sesi simulasi. Mulailah sekarang untuk memetakan pola keputusan investasi Anda.")
    elif session_count < 3:
        st.warning(
            f"Anda telah menyelesaikan {session_count} dari minimal 3 sesi. "
            f"Selesaikan {3 - session_count} sesi lagi agar analisis longitudinal lebih bermakna."
        )
    else:
        st.success(
            f"Anda telah menyelesaikan {session_count} sesi — cukup untuk analisis longitudinal. "
            f"Tambahkan sesi untuk memperkaya profil kognitif Anda."
        )

    with st.expander("Bagaimana sistem ini bekerja?", expanded=False):
        st.markdown(
            """
            Sistem ini dirancang untuk membantu investor ritel memahami pola
            pengambilan keputusan mereka melalui **simulasi investasi berbasis
            data historis saham IDX**.

            **Empat langkah proses:**

            1. **Simulasi** — Anda memainkan 14 putaran investasi menggunakan data historis saham IDX.
            2. **Analisis** — Sistem menghitung tiga metrik bias: *Efek Disposisi*, *Bias Keyakinan Berlebih (Overconfidence)*, dan *Kecenderungan Menghindari Kerugian (Loss Aversion)*.
            3. **Profil Kognitif** — Profil Anda diperbarui menggunakan *Cognitive Digital Twin* (CDT) berbasis Exponential Moving Average setelah setiap sesi.
            4. **Umpan Balik** — Anda menerima penjelasan yang kontekstual beserta langkah perbaikan yang praktis.
            """
        )


def _render_auth_flow() -> None:
    st.subheader("Selamat Datang")
    st.caption(
        "Masuk menggunakan nama pengguna Anda. Bila Anda pengguna baru, "
        "sistem akan memandu Anda melalui pendaftaran singkat."
    )

    stage = st.session_state.get("auth_stage", "username")

    if stage == "username":
        _render_auth_stage_username()
    elif stage == "login":
        _render_auth_stage_login()
    elif stage == "register":
        _render_auth_stage_register()


def _render_auth_stage_username() -> None:
    with st.form("cdt_username_form"):
        uname = st.text_input(
            "Nama Pengguna",
            value=st.session_state.get("auth_username", ""),
            max_chars=64,
            placeholder="Contoh: jaka.santoso",
        )
        submitted = st.form_submit_button("Lanjutkan →", type="primary", use_container_width=True)

    if submitted:
        uname_clean = (uname or "").strip()
        if len(uname_clean) < 2:
            st.error("Nama pengguna harus minimal 2 karakter.")
            return
        st.session_state["auth_username"] = uname_clean
        with get_session() as sess:
            exists = user_exists(sess, uname_clean)
        st.session_state["auth_stage"] = "login" if exists else "register"
        st.rerun()


def _render_auth_stage_login() -> None:
    uname = st.session_state.get("auth_username", "")
    st.markdown(f"**Nama pengguna:** `{uname}`")
    with st.form("cdt_login_form"):
        pwd = st.text_input("Kata Sandi", type="password", max_chars=128)
        col_a, col_b = st.columns([3, 1])
        with col_a:
            submitted = st.form_submit_button("Masuk", type="primary", use_container_width=True)
        with col_b:
            back = st.form_submit_button("← Ganti", use_container_width=True)

    if back:
        st.session_state["auth_stage"] = "username"
        st.rerun()
        return

    if submitted:
        try:
            with get_session() as sess:
                user = authenticate(sess, uname, pwd)
                uid, alias, exp = user.id, (user.alias or user.username), user.experience_level
        except RateLimitedError as e:
            st.error(str(e))
            return
        except InvalidCredentialsError:
            st.error("Nama pengguna atau kata sandi salah.")
            return
        except AuthError as e:
            st.error(str(e))
            return

        st.session_state["user_id"] = uid
        st.session_state["user_alias"] = alias
        st.session_state["experience_level"] = exp
        st.session_state["auth_stage"] = "username"
        st.session_state["auth_username"] = ""
        st.success(f"Selamat datang kembali, **{alias}**!")
        st.session_state["current_page"] = "Beranda"
        st.rerun()


def _render_auth_stage_register() -> None:
    uname = st.session_state.get("auth_username", "")
    st.markdown(
        f"Nama pengguna **`{uname}`** belum terdaftar. Silakan lengkapi "
        f"pendaftaran singkat di bawah."
    )

    with st.form("cdt_register_form"):
        st.markdown("#### Data Diri")
        col_a, col_b = st.columns(2)
        with col_a:
            full_name = st.text_input("Nama Lengkap", max_chars=128)
            age = st.number_input("Usia (tahun)", min_value=17, max_value=100, value=20, step=1)
        with col_b:
            gender = st.radio(
                "Jenis Kelamin",
                options=["laki-laki", "perempuan", "lainnya"],
                format_func=lambda x: x.title(),
                horizontal=True,
            )

        st.markdown("#### Profil Investor")
        risk_profile = st.radio(
            "Profil Risiko",
            options=["konservatif", "moderat", "agresif"],
            format_func=lambda x: x.capitalize(),
            help=(
                "**Konservatif:** memprioritaskan kestabilan modal. "
                "**Moderat:** menerima risiko terukur demi pertumbuhan. "
                "**Agresif:** bersedia menanggung fluktuasi besar untuk potensi tinggi."
            ),
            horizontal=True,
        )
        investing_capability = st.radio(
            "Pengalaman Investasi",
            options=["pemula", "menengah", "berpengalaman"],
            format_func=lambda x: x.capitalize(),
            help=(
                "**Pemula:** belum atau jarang berinvestasi saham. "
                "**Menengah:** aktif 1–3 tahun. "
                "**Berpengalaman:** aktif lebih dari 3 tahun atau berlatar belakang keuangan formal."
            ),
            horizontal=True,
        )

        st.markdown("#### Kata Sandi")
        pwd_a = st.text_input("Kata Sandi (min. 8 karakter)", type="password", max_chars=128)
        pwd_b = st.text_input("Ulangi Kata Sandi", type="password", max_chars=128)

        st.markdown("#### Survei Awal Kecenderungan Bias")
        st.caption(
            "Survei singkat ini membantu mengkalibrasi profil awal *Cognitive "
            "Digital Twin* Anda. Pilih nilai yang paling mendekati kecenderungan Anda."
        )
        survey_values: dict = {}
        for key, prompt in _ONBOARDING_ITEMS:
            survey_values[key] = st.select_slider(
                prompt,
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: _LIKERT_LABELS[x],
                key=f"onboard_{key}",
            )

        consent = st.checkbox(
            "Saya telah membaca informasi penelitian dan menyetujui partisipasi dalam penelitian ini.",
            value=False,
        )

        col_x, col_y = st.columns([3, 1])
        with col_x:
            submitted = st.form_submit_button(
                "Daftar & Mulai Simulasi", type="primary", use_container_width=True,
            )
        with col_y:
            back = st.form_submit_button("← Ganti", use_container_width=True)

    if back:
        st.session_state["auth_stage"] = "username"
        st.rerun()
        return

    if not submitted:
        return

    if pwd_a != pwd_b:
        st.error("Konfirmasi kata sandi tidak sesuai.")
        return
    if not consent:
        st.error("Anda harus menyetujui partisipasi untuk melanjutkan.")
        return

    try:
        with get_session() as sess:
            user = register_user(
                sess,
                username=uname,
                password=pwd_a,
                full_name=full_name,
                age=int(age),
                gender=gender,
                risk_profile=risk_profile,
                investing_capability=investing_capability,
                onboarding_survey=survey_values,
            )
            # Also persist a session_level-compatible UserSurvey row marked as
            # onboarding so the existing comparison engine works.
            from database.models import UserSurvey
            sess.add(UserSurvey(
                user_id=user.id,
                q_risk_tolerance=survey_values["ocs_q1"],
                q_loss_sensitivity=survey_values["lai_q1"],
                q_trading_frequency=survey_values["ocs_q2"],
                q_holding_behavior=survey_values["dei_q2"],
                survey_type="onboarding",
            ))
            uid, alias, exp = user.id, user.username, user.experience_level
        st.success(f"Akun **{uname}** berhasil dibuat. Selamat datang!")
    except DuplicateUsernameError:
        st.error("Nama pengguna sudah digunakan. Silakan pilih nama lain.")
        st.session_state["auth_stage"] = "username"
        return
    except WeakPasswordError as e:
        st.error(str(e))
        return
    except AuthError as e:
        st.error(str(e))
        return

    # Persist consent log
    try:
        from database.models import ConsentLog
        with get_session() as sess:
            sess.add(ConsentLog(
                user_id=uid,
                consent_given=True,
                consent_text="Saya telah membaca informasi penelitian dan menyetujui partisipasi.",
            ))
    except Exception:
        logger.warning("Failed to persist consent log for user %s", uid)

    st.session_state["user_id"] = uid
    st.session_state["user_alias"] = alias
    st.session_state["experience_level"] = exp
    st.session_state["auth_stage"] = "username"
    st.session_state["auth_username"] = ""
    st.session_state["current_page"] = "Simulasi Investasi"
    st.rerun()


# ---------------------------------------------------------------------------
# Page: Profil Kognitif Saya
# ---------------------------------------------------------------------------
def _page_profil() -> None:
    st.title("Profil Kognitif Saya")
    st.caption(
        "Representasi adaptif pola pengambilan keputusan investasi Anda, "
        "diperbarui setelah setiap sesi. Tersedia setelah sesi pertama selesai."
    )

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.warning("Silakan masuk terlebih dahulu.")
        return

    with get_session() as sess:
        profile = sess.query(CognitiveProfile).filter_by(user_id=user_id).first()
        past_metrics = (
            sess.query(BiasMetric)
            .filter_by(user_id=user_id)
            .order_by(BiasMetric.computed_at)
            .all()
        )
        metrics_data = [
            {
                "session_num": i + 1,
                "ocs": m.overconfidence_score or 0.0,
                "dei": abs(m.disposition_dei or 0.0),
                "dei_raw": m.disposition_dei or 0.0,
                "pgr": m.disposition_pgr or 0.0,
                "plr": m.disposition_plr or 0.0,
                "lai_norm": min((m.loss_aversion_index or 0.0) / 3.0, 1.0),
                "lai_raw": m.loss_aversion_index or 0.0,
                "computed_at": m.computed_at,
            }
            for i, m in enumerate(past_metrics)
        ]
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
        if profile:
            profile_data = {
                "bias_vector": dict(profile.bias_intensity_vector),
                "risk_preference": profile.risk_preference,
                "stability_index": profile.stability_index,
                "session_count": profile.session_count,
                "last_updated_at": profile.last_updated_at,
                "interaction_scores": profile.interaction_scores,
            }

    if profile_data is None:
        st.markdown(
            """
            <div style='border:1px solid #E5E7EB; border-radius:12px;
                        padding:32px; text-align:center; background:#FAFAFA;
                        margin-top:24px;'>
                <div style='font-size:36px; margin-bottom:12px;'>🧠</div>
                <div style='font-size:20px; font-weight:600;
                            color:#111827; margin-bottom:8px;'>
                    Profil Kognitif Belum Terbentuk
                </div>
                <div style='font-size:14px; color:#6B7280; margin-bottom:0px;'>
                    Profil Kognitif Digital Twin Anda akan terbentuk setelah
                    menyelesaikan sesi simulasi pertama.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
        if st.button("Mulai Sesi Simulasi →", type="primary", key="gate_profil_cta"):
            st.session_state["current_page"] = "Simulasi Investasi"
            st.rerun()
        return

    from modules.utils.ui_helpers import (
        apply_chart_theme, build_dual_radar_chart, BIAS_NAMES, SEVERITY_COLORS,
    )
    from modules.analytics.personal_baseline import compute_personal_thresholds

    st.markdown("### Profil Kognitif Digital Twin")
    st.caption(
        "Representasi adaptif pola pengambilan keputusan investasi Anda, "
        "diperbarui setelah setiap sesi."
    )

    c1, c2, c3 = st.columns(3)
    rp = profile_data["risk_preference"]
    rp_label = (
        "Agresif" if rp >= 0.6
        else "Moderat" if rp >= 0.3
        else "Konservatif"
    )
    si = profile_data["stability_index"]
    c1.metric("Total Sesi", profile_data["session_count"])
    c2.metric(
        "Indeks Stabilitas (Stability Index)",
        f"{si:.0%}",
        help="Seberapa konsisten pola bias Anda antar-sesi (100% = sangat konsisten).",
    )
    c3.metric(
        "Preferensi Risiko",
        rp_label,
        delta=f"Skor: {rp:.2f}",
        delta_color="off",
        help="Dihitung dari volatilitas saham yang Anda pilih, diperbarui tiap sesi dengan EMA.",
    )

    with st.expander("Apa itu Preferensi Risiko?"):
        st.markdown(
            """
            **Preferensi Risiko** mencerminkan seberapa sering Anda memilih saham
            bervolatilitas tinggi (misalnya ANTM, GOTO) dibandingkan saham
            konservatif (misalnya BBCA, TLKM).

            | Skor | Kategori | Arti |
            |------|----------|------|
            | 0,6 – 1,0 | Agresif | Sering memilih saham berisiko tinggi |
            | 0,3 – 0,6 | Moderat | Campuran saham berisiko sedang |
            | 0,0 – 0,3 | Konservatif | Cenderung memilih saham stabil |

            Nilai ini diperbarui menggunakan *Exponential Moving Average* (EMA)
            setelah setiap sesi sehingga mencerminkan tren terbaru perilaku Anda.
            """
        )

    st.divider()

    if metrics_data:
        latest = metrics_data[-1]
        current_scores = {
            "dei": latest["dei"],
            "ocs": latest["ocs"],
            "lai": latest["lai_norm"],
        }
        n = len(metrics_data)
        avg_scores = {
            "dei": sum(d["dei"] for d in metrics_data) / n,
            "ocs": sum(d["ocs"] for d in metrics_data) / n,
            "lai": sum(d["lai_norm"] for d in metrics_data) / n,
        }
        personal = compute_personal_thresholds(metrics_data)
        dual_radar = build_dual_radar_chart(
            current_scores,
            avg_scores,
            personal_thresholds=personal["values"],
            personal_threshold_is_fallback=personal["is_fallback"],
        )
        st.plotly_chart(dual_radar, use_container_width=True)
        st.caption(
            "Grafik radar menampilkan profil bias sesi terakhir (biru) dibanding "
            "rata-rata sesi Anda (oranye). Ring merah = **Titik Waspada Ilmiah** "
            "(ambang berat berdasarkan literatur). Ring biru putus-putus = "
            "**Titik Waspada Pribadi** (rata-rata + 1 deviasi standar dari riwayat Anda)."
        )

    bv = profile_data["bias_vector"]

    if len(metrics_data) >= 2:
        st.subheader("Riwayat Metrik per Sesi")
        sessions = [f"Sesi {d['session_num']}" for d in metrics_data]

        line_fig = go.Figure()
        line_fig.add_trace(go.Scatter(
            x=sessions, y=[d["ocs"] for d in metrics_data],
            mode="lines+markers", name="Bias Keyakinan Berlebih (OCS)",
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
            mode="lines+markers", name="Menghindari Kerugian (LAI, normalisasi)",
            line=dict(color=SEVERITY_COLORS["severe"], width=2),
            marker=dict(size=8),
        ))
        line_fig.update_yaxes(title_text="Intensitas Bias (0–1)", range=[0, 1])
        apply_chart_theme(line_fig, height=380)
        st.plotly_chart(line_fig, use_container_width=True)

    st.subheader("Insight")
    if bv:
        max_bias = max(bv, key=bv.get)
        max_val = bv[max_bias]
        bias_name = BIAS_NAMES.get(max_bias, max_bias)

        if max_val < 0.15:
            st.success(
                "Profil bias Anda menunjukkan pola pengambilan keputusan yang sehat "
                "secara keseluruhan. Pertahankan pendekatan analitis dalam setiap "
                "keputusan investasi."
            )
        elif max_val < 0.4:
            st.info(
                f"Kecenderungan tertinggi Anda saat ini adalah **{bias_name}** "
                f"(intensitas: {max_val:.2f}). Masih dalam batas ringan, namun "
                f"patut dipantau agar tidak meningkat di sesi berikutnya."
            )
        else:
            st.warning(
                f"Perhatian: **{bias_name}** menunjukkan intensitas {max_val:.2f}. "
                f"Fokuslah pada rekomendasi di halaman Hasil Analisis untuk "
                f"mengurangi kecenderungan ini."
            )

    if profile_data["last_updated_at"]:
        st.caption(f"Terakhir diperbarui: {fmt_datetime_wib(profile_data['last_updated_at'])}")

    st.divider()
    col_cta1, col_cta2 = st.columns(2)
    with col_cta1:
        if st.button("Lihat Umpan Balik Terakhir →", use_container_width=True):
            st.session_state["current_page"] = "Hasil Analisis & Umpan Balik"
            st.rerun()
    with col_cta2:
        if st.button("Mulai Sesi Baru →", use_container_width=True, type="primary"):
            st.session_state["current_page"] = "Simulasi Investasi"
            st.rerun()

    from modules.feedback.renderer import render_interaction_profile
    render_interaction_profile(user_id, snapshots_data)

    from modules.feedback.renderer import render_anomaly_detection_profile
    render_anomaly_detection_profile(user_id, profile_data["session_count"])

    st.divider()
    st.subheader("Ekspor Data")
    st.caption("Unduh data sesi untuk evaluasi dan analisis lebih lanjut.")

    import csv
    import io

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
            label="Unduh Riwayat Sesi (CSV)",
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
    st.title("Hasil Analisis & Umpan Balik")
    st.caption("Ringkasan bias kognitif, performa finansial, dan rekomendasi sesi terkini Anda.")

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.warning("Silakan masuk terlebih dahulu.")
        return

    # Use last_session_id from state; fall back to most recent completed session
    # in the database so returning users can always see their last feedback.
    session_id = st.session_state.get("last_session_id")
    if not session_id and user_id:
        with get_session() as sess:
            last_metric = (
                sess.query(BiasMetric)
                .filter_by(user_id=user_id)
                .order_by(BiasMetric.computed_at.desc())
                .first()
            )
            if last_metric:
                session_id = last_metric.session_id

    if not session_id:
        st.markdown(
            """
            <div style='border:1px solid #E5E7EB; border-radius:12px;
                        padding:32px; text-align:center; background:#FAFAFA;
                        margin-top:24px;'>
                <div style='font-size:36px; margin-bottom:12px;'>📊</div>
                <div style='font-size:20px; font-weight:600;
                            color:#111827; margin-bottom:8px;'>
                    Belum Ada Hasil Analisis
                </div>
                <div style='font-size:14px; color:#6B7280; margin-bottom:0px;'>
                    Selesaikan seluruh <b>14 putaran</b> dalam satu sesi
                    simulasi untuk membuka analisis bias dan umpan balik Anda.
                    Meninggalkan simulasi di tengah jalan tidak menyimpan hasil.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
        if st.button("Mulai Sesi Simulasi →", type="primary", key="gate_hasil_cta"):
            st.session_state["current_page"] = "Simulasi Investasi"
            st.rerun()
        return

    render_feedback_page(user_id=user_id, session_id=session_id)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def main() -> None:
    _init_session_state()
    inject_custom_css()

    _render_header()

    page = st.session_state["current_page"]

    if page == "Beranda":
        _page_beranda()
    elif page == "Simulasi Investasi":
        if not st.session_state.get("user_id"):
            st.warning("Silakan masuk terlebih dahulu di halaman Beranda.")
            return
        render_simulation_page()
    elif page == "Hasil Analisis & Umpan Balik":
        _page_hasil()
    elif page == "Profil Kognitif Saya":
        _page_profil()


if __name__ == "__main__":
    main()
