"""
modules/feedback/renderer.py — Streamlit feedback display components.

Functions:
    render_feedback_page       — Full post-session feedback page.
    render_bias_card           — Single bias card with severity badge.
    render_longitudinal_section — Session-over-session comparison strip.
"""

from __future__ import annotations

import streamlit as st

from config import (
    DEI_MILD, DEI_MODERATE, DEI_SEVERE,
    LAI_MILD, LAI_MODERATE, LAI_SEVERE,
    OCS_MILD, OCS_MODERATE, OCS_SEVERE,
)
from database.connection import get_session
from database.models import BiasMetric
from modules.analytics.bias_metrics import classify_severity
from modules.feedback.generator import (
    generate_tldr_summary,
    get_longitudinal_summary,
    get_session_feedback,
)
from modules.utils.ui_helpers import (
    BIAS_DESCRIPTIONS,
    BIAS_NAMES,
    SEVERITY_BG,
    SEVERITY_COLORS,
    SEVERITY_ICONS,
    SEVERITY_LABELS,
    build_severity_gauge,
)

# ---------------------------------------------------------------------------
# Backward-compatible aliases (used by tests)
# ---------------------------------------------------------------------------

_SEVERITY_COLOUR = {
    "severe": "🔴",
    "moderate": "🟠",
    "mild": "🟡",
    "none": "🟢",
}

_SEVERITY_LABEL = SEVERITY_LABELS

_BIAS_DISPLAY_NAME = BIAS_NAMES

_SEVERITY_ORDER = ["none", "mild", "moderate", "severe"]


def _severity_delta(prev: str, curr: str) -> str:
    """Return a delta string comparing two severity labels (Bahasa Indonesia)."""
    prev_idx = _SEVERITY_ORDER.index(prev) if prev in _SEVERITY_ORDER else 0
    curr_idx = _SEVERITY_ORDER.index(curr) if curr in _SEVERITY_ORDER else 0
    prev_label = SEVERITY_LABELS.get(prev, prev)
    curr_label = SEVERITY_LABELS.get(curr, curr)
    if curr_idx < prev_idx:
        return f"Sesi lalu: {prev_label} → Sesi ini: {curr_label} ↓ (membaik)"
    elif curr_idx > prev_idx:
        return f"Sesi lalu: {prev_label} → Sesi ini: {curr_label} ↑ (meningkat)"
    return f"Sesi lalu: {prev_label} → Sesi ini: {curr_label} (tetap)"


def render_bias_card(
    bias_type: str,
    severity: str,
    explanation: str,
    recommendation: str,
    prev_severity: str | None = None,
) -> None:
    """Render a single bias feedback card with colour-coded left border.

    Args:
        bias_type:      e.g. "disposition_effect".
        severity:       "none", "mild", "moderate", or "severe".
        explanation:    Explanation text (Bahasa Indonesia).
        recommendation: Recommendation text (Bahasa Indonesia).
        prev_severity:  Severity from the previous session, if available.
    """
    color = SEVERITY_COLORS.get(severity, "#5F6368")
    bg = SEVERITY_BG.get(severity, "rgba(0,0,0,0.03)")
    icon = SEVERITY_ICONS.get(severity, "⚪")
    label = SEVERITY_LABELS.get(severity, severity)
    title = BIAS_NAMES.get(bias_type, bias_type.replace("_", " ").title())
    desc = BIAS_DESCRIPTIONS.get(bias_type, "")

    # Styled card header with colored left border (light theme)
    st.markdown(
        f"""
        <div style="
            border-left: 4px solid {color};
            background: {bg};
            border: 1px solid #E5E7EB;
            border-left-width: 4px;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 4px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-size: 17px; font-weight: 600; color: #1C1E21;">
                    {icon} {title}
                </span>
                <span style="
                    background: {color}22;
                    color: {color};
                    padding: 3px 10px;
                    border-radius: 12px;
                    font-size: 12px;
                    font-weight: 500;
                ">{label}</span>
            </div>
            <p style="color: #5F6368; font-size: 12px; margin: 0;">{desc}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Expander for detail content (expanded for non-none severity)
    with st.expander(f"{icon} {title} — {label}", expanded=(severity != "none")):
        if prev_severity is not None:
            delta_str = _severity_delta(prev_severity, severity)
            st.caption(delta_str)

        # Methodology block — shows formula + literature source.
        # Rendered as HTML <details> rather than a nested st.expander to keep
        # the outer-expander call unique (test contract).
        formula_info = _BIAS_FORMULA.get(bias_type)
        if formula_info:
            components_html = (
                formula_info["components"].replace("\n", "<br>")
            )
            st.markdown(
                f"""
                <details style="margin:10px 0; padding:10px 14px;
                                border:1px solid #E5E7EB; border-radius:6px;
                                background:rgba(0,0,0,0.02);">
                    <summary style="cursor:pointer; font-weight:600; color:#1C1E21;">
                        📐 Cara Pengukuran: {formula_info['name_en']}
                    </summary>
                    <div style="margin-top:10px; font-size:14px; line-height:1.6;">
                        <div><b>Rumus:</b>
                            <code>{formula_info['formula']}</code>
                        </div>
                        <div style="margin-top:6px; padding:8px 10px;
                                    background:#F3F4F6; border-radius:4px;
                                    font-family: ui-monospace, SFMono-Regular, monospace;
                                    font-size:12px; white-space:pre-wrap;">
                            {components_html}
                        </div>
                        <div style="margin-top:8px;">
                            <b>Interpretasi:</b> {formula_info['interpretation']}
                        </div>
                        <div style="margin-top:6px;">
                            <b>Referensi ilmiah:</b> {formula_info['citation']}
                        </div>
                    </div>
                </details>
                """,
                unsafe_allow_html=True,
            )

        if severity == "none":
            st.success(explanation)
        else:
            st.markdown("**Penjelasan:**")
            st.info(explanation)
            st.markdown("**Rekomendasi:**")
            st.warning(recommendation)


def render_longitudinal_section(user_id: int) -> None:
    """Show session-over-session severity history as a compact table + visual timeline.

    Args:
        user_id: ID of the user.
    """
    with get_session() as sess:
        summary = get_longitudinal_summary(sess, user_id)

    if len(summary["sessions"]) < 2:
        return

    st.markdown("---")
    st.subheader("📈 Perjalanan Bias Antar Sesi")
    st.caption("Warna menunjukkan intensitas bias dari sesi ke sesi. Penurunan = perbaikan.")

    # Table format (backward-compatible with tests)
    rows = []
    for i, _ in enumerate(summary["sessions"], start=1):
        row = {"Sesi": f"Sesi {i}"}
        for bias_type in ["disposition_effect", "overconfidence", "loss_aversion"]:
            sev = (
                summary["trend"][bias_type][i - 1]
                if i - 1 < len(summary["trend"][bias_type])
                else "none"
            )
            emoji = _SEVERITY_COLOUR.get(sev, "⚪")
            row[BIAS_NAMES[bias_type]] = f"{emoji} {SEVERITY_LABELS.get(sev, sev)}"
        rows.append(row)

    st.table(rows)

    # Visual color-coded timeline per bias (additional polish)
    n_sessions = len(summary["sessions"])
    for bias_type in ["disposition_effect", "overconfidence", "loss_aversion"]:
        title = BIAS_NAMES.get(bias_type, bias_type)
        st.markdown(f"**{title}**")
        cols = st.columns(min(n_sessions, 8))
        trend = summary["trend"].get(bias_type, [])
        for i, col in enumerate(cols):
            if i < len(trend):
                sev = trend[i]
                clr = SEVERITY_COLORS.get(sev, "#78909c")
                lbl = SEVERITY_LABELS.get(sev, sev)
                col.markdown(
                    f"<div style='text-align:center; padding:6px; "
                    f"border-radius:8px; background:{clr}22; "
                    f"border: 1px solid {clr}44;'>"
                    f"<div style='font-size:10px; color:#90A4AE;'>Sesi {i + 1}</div>"
                    f"<div style='font-size:12px; color:{clr}; font-weight:600;'>{lbl}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


INTERACTION_TEASER_THRESHOLD_SESSIONS = 5


def render_interaction_teaser(session_count: int) -> None:
    """Render a teaser for the interaction/anomaly module before session 5."""
    remaining = max(0, INTERACTION_TEASER_THRESHOLD_SESSIONS - session_count)
    st.markdown("---")
    st.markdown(
        f"""
        <div style="
            background: rgba(37, 99, 235, 0.05);
            border: 1px solid rgba(37, 99, 235, 0.25);
            border-radius: 10px;
            padding: 18px 22px;
        ">
            <div style="font-size:16px; font-weight:700; color:#2563EB; margin-bottom:8px;">
                🔒 Buka Insight Mendalam di Sesi ke-5
            </div>
            <div style="color:#1F2937; font-size:14px; line-height:1.7;">
                Setelah Anda menyelesaikan <b>5 sesi simulasi</b>, Anda akan menerima:
                <ul style='margin:8px 0 8px 18px; padding:0;'>
                    <li><b>Peta Interaksi Antar-Bias</b> (<i>Bias Interaction Map</i>) — koefisien korelasi
                        Pearson antara Efek Disposisi, Bias Keyakinan Berlebih, dan Kecenderungan
                        Menghindari Kerugian, untuk mengungkap bias majemuk yang unik pada Anda.</li>
                    <li><b>Deteksi Anomali</b> (<i>ML-Validated Anomaly Detection</i>) — identifikasi
                        keputusan yang menyimpang dari pola pribadi Anda.</li>
                </ul>
                Sesi tersisa: <b>{remaining}</b>.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _translate_top_correlation(interaction_scores: dict) -> str | None:
    """Produce a plain-language Bahasa narrative for the strongest pairwise r."""
    if not interaction_scores:
        return None
    _PAIR_LABELS = {
        "ocs_dei": ("bias Keyakinan Berlebih", "Efek Disposisi"),
        "ocs_lai": ("bias Keyakinan Berlebih", "kecenderungan Menghindari Kerugian"),
        "dei_lai": ("Efek Disposisi", "kecenderungan Menghindari Kerugian"),
    }
    ranked = sorted(
        (
            (k, v) for k, v in interaction_scores.items()
            if v is not None and k in _PAIR_LABELS
        ),
        key=lambda kv: abs(kv[1]),
        reverse=True,
    )
    if not ranked:
        return None
    key, r = ranked[0]
    a, b = _PAIR_LABELS[key]
    if abs(r) < 0.30:
        return (
            f"Korelasi antar-bias Anda masih lemah (r = {r:+.2f}) — belum ada "
            f"pola gabungan yang mencolok antara {a} dan {b}."
        )
    direction = "ikut meningkat" if r > 0 else "justru menurun"
    return (
        f"Ketika {a} Anda meningkat, {b} cenderung {direction} "
        f"(r = {r:+.2f}). Kedua bias ini saling terkait dalam pola keputusan "
        f"Anda — waspada terhadap siklus umpan balik ini."
    )


def render_interaction_synthesis(user_id: int, session_id: str) -> None:
    """Render the interaction heatmap + narrative at session 5+, or a teaser before that.

    The teaser is always shown for sessions 1–4 so users understand what
    unlocks at session 5. From session 5 onward the full synthesis renders.
    """
    from database.models import CognitiveProfile
    from modules.feedback.generator import _get_interaction_modifier

    with get_session() as sess:
        profile = sess.query(CognitiveProfile).filter_by(user_id=user_id).first()
        if profile is None:
            # Profile not yet committed — show teaser for first-session users
            render_interaction_teaser(0)
            return
        session_count = profile.session_count
        interaction_scores = profile.interaction_scores
        stability_index = profile.stability_index

    if session_count < INTERACTION_TEASER_THRESHOLD_SESSIONS:
        render_interaction_teaser(session_count)
        return

    class _ProfileSnapshot:
        pass

    snap = _ProfileSnapshot()
    snap.session_count = session_count
    snap.interaction_scores = interaction_scores
    snap.stability_index = stability_index

    insights = _get_interaction_modifier(snap)  # type: ignore[arg-type]

    st.markdown("---")
    st.subheader("🔗 Pola Bias Gabungan")
    st.caption(
        "Analisis keterkaitan antar-bias berdasarkan riwayat multi-sesi Anda. "
        "Pola ini menjadi stabil setelah minimal 5 sesi selesai."
    )

    narrative = _translate_top_correlation(interaction_scores or {})
    if narrative:
        st.info(narrative)

    for insight in insights or []:
        st.info(insight)


def render_interaction_profile(user_id: int, snapshots_data: list[dict]) -> None:
    """Render the bias interaction panel for the Profil Kognitif Saya page.

    Shows the teaser (sessions 1–4) or the full correlation heatmap + narrative
    (session 5+). Uses CdtSnapshot history for the heatmap scatter overlay.

    The Pearson correlation method (Barber & Odean, 2000; Shefrin & Statman, 1985)
    quantifies how strongly two bias dimensions co-move across sessions. A value
    of r = +0.8 means the two biases tend to be simultaneously high or low,
    suggesting a compound behavioral pattern.

    Args:
        user_id:        User ID.
        snapshots_data: List of serialised CdtSnapshot dicts
                        (keys: session_number, cdt_overconfidence, cdt_disposition).
    """
    from modules.cdt.interaction import build_interaction_heatmap_data
    from modules.feedback.generator import _get_interaction_modifier
    import plotly.graph_objects as go

    with get_session() as sess:
        from database.models import CognitiveProfile
        profile = sess.query(CognitiveProfile).filter_by(user_id=user_id).first()
        if profile is None:
            render_interaction_teaser(0)
            return
        session_count = profile.session_count
        interaction_scores = profile.interaction_scores or {}
        stability_index = profile.stability_index

    st.markdown("---")
    st.subheader("🔗 Pola Bias Gabungan (Lintas Sesi)")
    st.caption(
        "Mengukur seberapa erat ketiga bias Anda bergerak bersama di seluruh riwayat sesi. "
        "Pola ini menjadi bermakna setelah minimal 5 sesi selesai."
    )

    if session_count < INTERACTION_TEASER_THRESHOLD_SESSIONS:
        render_interaction_teaser(session_count)
        return

    # --- Methodology explainer ---
    with st.expander("📐 Metode: Korelasi Pearson Antar-Bias", expanded=False):
        st.markdown(
            """
            **Rumus:** r(X, Y) = Σ[(Xᵢ − X̄)(Yᵢ − Ȳ)] / [(n−1) · σₓ · σᵧ]

            **Interpretasi:**
            - |r| < 0.30 → korelasi lemah (tidak ada pola gabungan signifikan)
            - 0.30 ≤ |r| < 0.70 → korelasi moderat
            - |r| ≥ 0.70 → korelasi kuat (bias cenderung muncul bersama)

            Korelasi dihitung dari riwayat bias lintas sesi Anda menggunakan
            window `CDT_STABILITY_WINDOW` sesi terakhir. Pendekatan ini mengadaptasi
            metode analisis perilaku investor dari **Barber & Odean (2000)** dan
            **Shefrin & Statman (1985)** ke dalam kerangka *Cognitive Digital Twin*.

            **Referensi:**
            - Barber, B. M., & Odean, T. (2000). *Trading is hazardous to your wealth.*
              Journal of Finance, 55(2), 773–806.
            - Shefrin, H., & Statman, M. (1985). *The disposition to sell winners too early
              and ride losers too long.* Journal of Finance, 40(3), 777–790.
            """
        )

    # --- Correlation narrative ---
    narrative = _translate_top_correlation(interaction_scores)
    if narrative:
        st.info(narrative)

    class _ProfileSnap:
        pass
    snap = _ProfileSnap()
    snap.session_count = session_count
    snap.interaction_scores = interaction_scores
    snap.stability_index = stability_index
    for insight in (_get_interaction_modifier(snap) or []):  # type: ignore[arg-type]
        st.info(insight)

    # --- Heatmap (DEI × OCS) using CdtSnapshot history ---
    if len(snapshots_data) >= 2:
        hd = build_interaction_heatmap_data(snapshots_data)

        fig = go.Figure()
        # Background severity gradient
        fig.add_trace(go.Heatmap(
            x=hd["x"],
            y=hd["y"],
            z=hd["z"],
            colorscale=[
                [0.0,  "rgba(37,99,235,0.15)"],
                [0.5,  "rgba(227,116,0,0.25)"],
                [1.0,  "rgba(197,34,31,0.40)"],
            ],
            showscale=True,
            colorbar=dict(
                title="Intensitas Gabungan",
                tickfont=dict(size=10),
                len=0.6,
            ),
            hoverinfo="skip",
        ))
        # User trajectory scatter
        fig.add_trace(go.Scatter(
            x=hd["scatter_x"],
            y=hd["scatter_y"],
            mode="lines+markers+text",
            text=hd["scatter_labels"],
            textposition="top center",
            textfont=dict(size=11, color="#1C1E21"),
            marker=dict(size=10, color="#2563EB", line=dict(color="#fff", width=1.5)),
            line=dict(color="#2563EB", width=1.5, dash="dot"),
            hovertext=hd["scatter_text"],
            hoverinfo="text",
            name="Sesi Anda",
        ))
        fig.update_layout(
            xaxis_title="|Efek Disposisi (DEI)|",
            yaxis_title="Overconfidence (OCS)",
            height=400,
            margin=dict(l=10, r=10, t=30, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#4A4A4A", size=12),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Setiap titik mewakili satu sesi. Posisi kanan-atas = kombinasi DEI+OCS tinggi. "
            "Gradien latar: biru = intensitas gabungan rendah, merah = tinggi."
        )

    # Pairwise correlation table
    _PAIR_LABELS_ID = {
        "ocs_dei": ("OCS", "DEI"),
        "ocs_lai": ("OCS", "LAI"),
        "dei_lai": ("DEI", "LAI"),
    }
    if interaction_scores:
        st.markdown("**Koefisien Korelasi Pearson Antar-Bias:**")
        cols_corr = st.columns(3)
        for col, (key, (a, b)) in zip(cols_corr, _PAIR_LABELS_ID.items()):
            r = interaction_scores.get(key)
            if r is not None:
                strength = "Kuat" if abs(r) >= 0.7 else "Moderat" if abs(r) >= 0.3 else "Lemah"
                direction = "positif" if r > 0 else "negatif"
                col.metric(
                    f"{a} ↔ {b}",
                    f"r = {r:+.2f}",
                    delta=f"{strength} ({direction})",
                    delta_color="off",
                )
            else:
                col.metric(f"{a} ↔ {b}", "—", delta="Variansi nol")


ANOMALY_THRESHOLD_SESSIONS = 5  # mirrors _MIN_SESSIONS_FOR_ML in ml_validator


def render_anomaly_detection_profile(user_id: int, session_count: int) -> None:
    """Render the Isolation Forest anomaly detection panel on the profile page.

    Shows teaser before 5 sessions; full panel with per-session anomaly chart
    and methodology explainer at 5+ sessions.

    Isolation Forest (Liu et al., 2008) detects sessions that are easier to
    isolate from the user's own behavioral cluster — indicating an unusually
    extreme or atypical bias combination relative to YOUR own baseline.

    Args:
        user_id:       User ID.
        session_count: Current session count from CognitiveProfile.
    """
    from modules.cdt.ml_validator import compute_anomaly_flags

    st.markdown("---")
    st.subheader("🔍 Deteksi Anomali Keputusan (ML)")
    st.caption(
        "Identifikasi sesi di mana pola bias Anda menyimpang secara signifikan "
        "dari kebiasaan Anda sendiri, divalidasi menggunakan metode machine learning."
    )

    if session_count < ANOMALY_THRESHOLD_SESSIONS:
        remaining = max(0, ANOMALY_THRESHOLD_SESSIONS - session_count)
        st.markdown(
            f"""
            <div style="background:rgba(37,99,235,0.05); border:1px solid rgba(37,99,235,0.25);
                        border-radius:10px; padding:18px 22px;">
                <div style="font-size:16px; font-weight:700; color:#2563EB; margin-bottom:8px;">
                    🔒 Tersedia di Sesi ke-5
                </div>
                <div style="color:#1F2937; font-size:14px; line-height:1.7;">
                    Setelah Anda menyelesaikan <b>5 sesi simulasi</b>, sistem akan
                    mengaktifkan <b>Isolation Forest</b> — algoritma ML yang mendeteksi
                    sesi di mana kombinasi bias Anda menyimpang dari pola kebiasaan Anda sendiri.<br><br>
                    Sesi tersisa: <b>{remaining}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # --- Methodology explainer ---
    with st.expander("📐 Metode: Isolation Forest (Liu et al., 2008)", expanded=False):
        st.markdown(
            """
            **Cara kerja Isolation Forest:**
            Algoritma ini membangun pohon keputusan acak (*random isolation trees*) dan
            mengukur seberapa mudah sebuah titik data dapat "diisolasi" dari yang lain.
            Data yang anomali biasanya dapat diisolasi lebih cepat (jalur lebih pendek
            di pohon), sehingga menghasilkan skor anomali lebih negatif.

            **Fitur yang digunakan (3 dimensi, dinormalisasi ke [0, 1]):**
            - OCS (Overconfidence Score)
            - |DEI| (Efek Disposisi, nilai absolut)
            - LAI_norm = min(LAI / LAI_ceiling, 1.0)

            **Interpretasi skor:**
            - Skor lebih negatif → sesi lebih anomali dibanding baseline pribadi Anda
            - Threshold: skor < 0 → sesi diflag sebagai anomali
            - `contamination = 0.10`: asumsi ~10% sesi adalah outlier struktural

            **Catatan penting:** Deteksi ini bersifat *per-user* — bukan dibandingkan
            dengan pengguna lain, melainkan dibandingkan dengan **pola Anda sendiri**.
            Sesi anomali bukan berarti "salah", tetapi menandakan pola yang tidak biasa
            bagi Anda secara individual.

            **Referensi:**
            Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). *Isolation forest.*
            Proceedings of the 8th IEEE International Conference on Data Mining (ICDM),
            413–422. https://doi.org/10.1109/ICDM.2008.17
            """
        )

    # --- Run anomaly detection ---
    with get_session() as sess:
        anomaly_result = compute_anomaly_flags(sess, user_id)

    if anomaly_result is None:
        st.info(
            "Data sesi belum mencukupi untuk menjalankan deteksi anomali "
            "(minimal 5 sesi diperlukan)."
        )
        return

    session_ids = anomaly_result["session_ids"]
    scores = anomaly_result["anomaly_scores"]
    flags = anomaly_result["is_anomaly"]
    n = anomaly_result["n_sessions"]
    n_anomalies = sum(flags)

    # Summary metric
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Sesi Dianalisis", n)
    col_b.metric(
        "Sesi Anomali Terdeteksi",
        n_anomalies,
        delta=(
            "Tidak ada anomali — pola konsisten ✓"
            if n_anomalies == 0
            else f"{n_anomalies / n:.0%} dari total sesi"
        ),
        delta_color="normal" if n_anomalies == 0 else "inverse",
    )
    col_c.metric(
        "Skor Rata-rata",
        f"{sum(scores)/len(scores):.3f}",
        help="Skor rata-rata Isolation Forest. Lebih negatif = lebih anomali secara keseluruhan.",
        delta_color="off",
    )

    # Per-session bar chart of anomaly scores
    import plotly.graph_objects as go
    session_labels = [f"Sesi {i+1}" for i in range(n)]
    bar_colors = [
        SEVERITY_COLORS["severe"] if f else SEVERITY_COLORS["none"]
        for f in flags
    ]
    fig = go.Figure(go.Bar(
        x=session_labels,
        y=scores,
        marker_color=bar_colors,
        hovertemplate=(
            "%{x}<br>Skor Anomali: %{y:.4f}<br>"
            "<extra></extra>"
        ),
    ))
    # Threshold line at y=0
    fig.add_hline(
        y=0, line_dash="dash", line_color="#E37400", line_width=1.5,
        annotation_text="Batas anomali (skor < 0)",
        annotation_position="top right",
        annotation_font_size=11,
    )
    fig.update_layout(
        yaxis_title="Skor Anomali (lebih negatif = lebih menyimpang)",
        height=300,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#4A4A4A", size=12),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "🔴 Batang merah = sesi yang diflag anomali (skor < 0). "
        "🟢 Batang hijau = sesi normal. "
        "Garis oranye = batas deteksi anomali."
    )

    # Per-session anomaly detail
    if n_anomalies > 0:
        st.markdown("**Sesi Anomali:**")
        for i, (sid, score, is_flag) in enumerate(
            zip(session_ids, scores, flags)
        ):
            if is_flag:
                st.warning(
                    f"⚠️ **Sesi {i+1}** (`{sid[:8]}…`) — "
                    f"Skor anomali: `{score:.4f}`. "
                    f"Kombinasi bias pada sesi ini menyimpang dari pola kebiasaan Anda."
                )
    else:
        st.success(
            "✅ Tidak ada sesi anomali terdeteksi. "
            "Pola bias Anda cukup konsisten di seluruh sesi."
        )


def render_anomaly_session_flag(user_id: int, session_id: str) -> None:
    """Render a compact anomaly flag for the current session on the feedback page.

    Only shows when session_count >= 5 and anomaly detection produces a result.
    Shows a green "normal" badge or an amber "anomali terdeteksi" alert.

    Args:
        user_id:    User ID.
        session_id: Current session UUID.
    """
    from modules.cdt.ml_validator import compute_anomaly_flags

    with get_session() as sess:
        anomaly_result = compute_anomaly_flags(sess, user_id)

    if anomaly_result is None:
        return  # Not enough sessions yet — teaser is handled by render_interaction_synthesis

    try:
        idx = anomaly_result["session_ids"].index(session_id)
    except ValueError:
        return  # Current session not yet in the anomaly history (edge case)

    score = anomaly_result["anomaly_scores"][idx]
    is_flag = anomaly_result["is_anomaly"][idx]

    st.markdown("---")
    st.markdown("#### 🔍 Deteksi Anomali Sesi Ini")
    if is_flag:
        st.warning(
            f"**Sesi ini terdeteksi sebagai anomali** oleh model Isolation Forest "
            f"(skor: `{score:.4f}`). Kombinasi bias Anda pada sesi ini menyimpang "
            f"secara signifikan dari pola kebiasaan Anda sendiri. "
            f"Tinjau lebih lanjut di halaman **Profil Kognitif Saya**."
        )
    else:
        st.success(
            f"Sesi ini terdeteksi sebagai **normal** (skor: `{score:.4f}`). "
            f"Pola bias Anda konsisten dengan kebiasaan Anda."
        )


_PILL_SEVERITY_LABEL = {
    "none": "Tidak Ada",
    "mild": "Ringan",
    "moderate": "Sedang",
    "severe": "Berat",
}

_PILL_SEVERITY_COLOR = {
    "none": ("#52C41A", "rgba(82,196,26,0.15)"),
    "mild": ("#4A90E2", "rgba(74,144,226,0.15)"),
    "moderate": ("#F5A623", "rgba(245,166,35,0.15)"),
    "severe": ("#E8553A", "rgba(232,85,58,0.15)"),
}

_BIAS_SHORT_KEY = {
    "disposition_effect": "dei",
    "overconfidence": "ocs",
    "loss_aversion": "lai",
}


# Scientific formula references for each bias type — shown in feedback cards.
_BIAS_FORMULA = {
    "disposition_effect": {
        "name_en": "Disposition Effect Index (DEI)",
        "formula": "DEI = PGR − PLR",
        "components": (
            "PGR = Realized Gains / (Realized Gains + Paper Gains)\n"
            "PLR = Realized Losses / (Realized Losses + Paper Losses)"
        ),
        "interpretation": (
            "DEI > 0: kecenderungan merealisasi keuntungan lebih cepat dari kerugian. "
            "DEI < 0: pola berlawanan (jarang). |DEI| ≥ 0.50 dikategorikan Berat."
        ),
        "citation": "Odean, T. (1998). *Are investors reluctant to realize their losses?* "
                    "Journal of Finance, 53(5), 1775–1798.",
    },
    "overconfidence": {
        "name_en": "Overconfidence Score (OCS)",
        "formula": "OCS = σ(trade_frequency / max(performance_ratio, 0.01))",
        "components": (
            "trade_frequency = (buy + sell) / 14 putaran\n"
            "performance_ratio = realized P&L / modal awal\n"
            "σ = fungsi sigmoid — membatas OCS ke rentang [0, 1)"
        ),
        "interpretation": (
            "OCS tinggi tanpa return proporsional mengindikasikan kepercayaan diri "
            "berlebih: banyak bertransaksi tetapi tidak menghasilkan performa optimal. "
            "OCS ≥ 0.70 dikategorikan Berat."
        ),
        "citation": "Barber, B. M., & Odean, T. (2000). *Trading is hazardous to your wealth.* "
                    "Journal of Finance, 55(2), 773–806.",
    },
    "loss_aversion": {
        "name_en": "Loss Aversion Index (LAI)",
        "formula": "LAI = avg_hold_losers / max(avg_hold_winners, 1.0)",
        "components": (
            "avg_hold_losers = rata-rata putaran bertahan di posisi merugi\n"
            "avg_hold_winners = rata-rata putaran bertahan di posisi untung"
        ),
        "interpretation": (
            "LAI > 1.0: Anda menahan posisi merugi lebih lama dari posisi untung. "
            "LAI ≥ 2.0 dikategorikan Berat dan mencerminkan asimetri perilaku signifikan."
        ),
        "citation": "Kahneman, D., & Tversky, A. (1979). *Prospect theory: An analysis of "
                    "decision under risk.* Econometrica, 47(2), 263–291.",
    },
}


def _render_session_results(
    feedbacks: list[dict],
    metric_data: dict,
    user_id: int,
    session_id: str,
) -> None:
    """Render 'Hasil Sesi Ini' — financial performance cards + bias summary text.

    Replaces the old amber TL;DR box. Financial metrics are loaded live from
    extract_session_features; bias summary text is kept but without the orange
    container, rendered in plain markdown.
    """
    from modules.analytics.features import extract_session_features

    # --- Build bias_results for generate_tldr_summary ---
    bias_results: dict[str, tuple[float, str]] = {}
    for fb in feedbacks:
        short = _BIAS_SHORT_KEY.get(fb["bias_type"])
        if short:
            bias_results[short] = (metric_data[short], fb["severity"])
    for k in ("dei", "ocs", "lai"):
        bias_results.setdefault(k, (0.0, "none"))

    tldr_text = generate_tldr_summary(bias_results)

    # --- Section title ---
    st.markdown("### 📈 Hasil Sesi Ini")

    # --- Financial metric cards ---
    try:
        with get_session() as sess:
            sf = extract_session_features(sess, user_id, session_id)

        # Derive cash: final_value − market value of open positions
        open_market_val = sum(
            p["final_price"] * p["quantity"] for p in sf.open_positions
        )
        final_cash = sf.final_value - open_market_val
        realized_pnl = sum(
            (t["sell_price"] - t["buy_price"]) * t["quantity"]
            for t in sf.realized_trades
        )
        unrealized_pnl = sum(p["unrealized_pnl"] for p in sf.open_positions)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Realized P&L",
            f"Rp {realized_pnl:+,.0f}",
            delta=("Untung" if realized_pnl > 0 else "Rugi" if realized_pnl < 0 else "Impas"),
            delta_color="normal" if realized_pnl >= 0 else "inverse",
            help="Laba/rugi yang sudah terealisasi dari posisi yang ditutup pada sesi ini.",
        )
        c2.metric(
            "Saldo Kas Akhir",
            f"Rp {final_cash:,.0f}",
            help="Saldo kas tunai yang tersisa setelah semua transaksi sesi ini.",
        )
        c3.metric(
            "Nilai Posisi Terbuka",
            f"Rp {open_market_val:,.0f}",
            delta=f"Unrealized: Rp {unrealized_pnl:+,.0f}",
            delta_color="normal" if unrealized_pnl >= 0 else "inverse",
            help="Nilai pasar saat ini dari semua posisi yang masih terbuka.",
        )
        c4.metric(
            "Return Portofolio",
            f"{sf.portfolio_return_pct:+.1f}%",
            help="Return keseluruhan portofolio dibandingkan modal awal sesi.",
        )

        # Open positions detail (compact, below cards)
        if sf.open_positions:
            with st.expander("Rincian Posisi Terbuka", expanded=False):
                for p in sf.open_positions:
                    icon = "🟢" if p["unrealized_pnl"] >= 0 else "🔴"
                    sign = "+" if p["unrealized_pnl"] >= 0 else ""
                    st.caption(
                        f"{icon} **{p['stock_id'].split('.')[0]}**: "
                        f"{p['quantity']} lbr @ Rp {p['avg_price']:,.0f}  •  "
                        f"Harga akhir: Rp {p['final_price']:,.0f}  •  "
                        f"Unrealized: {sign}Rp {p['unrealized_pnl']:,.0f}"
                    )

    except Exception:
        import logging as _log
        _log.getLogger(__name__).warning(
            "Failed to load session features for financial summary "
            "user=%s session=%s", user_id, session_id, exc_info=True
        )
        st.caption("Data finansial sesi tidak tersedia.")

    # --- Bias summary text (plain, no orange box) ---
    st.divider()
    st.markdown(tldr_text)

    # --- Bias severity pills ---
    pill_cols = st.columns(3)
    pill_labels = [
        ("DEI", bias_results["dei"][1]),
        ("OCS", bias_results["ocs"][1]),
        ("LAI", bias_results["lai"][1]),
    ]
    for col, (badge_key, sev) in zip(pill_cols, pill_labels):
        color, bg = _PILL_SEVERITY_COLOR.get(sev, ("#78909c", "rgba(120,144,156,0.15)"))
        label = _PILL_SEVERITY_LABEL.get(sev, sev.capitalize())
        col.markdown(
            f"<div style='"
            f"display:inline-block; padding:4px 14px; border-radius:20px; "
            f"background:{bg}; border:1px solid {color}44; "
            f"color:{color}; font-size:13px; font-weight:600;'>"
            f"{badge_key}: {label}</div>",
            unsafe_allow_html=True,
        )


def render_feedback_page(user_id: int, session_id: str) -> None:
    """Render the complete post-session feedback page.

    Args:
        user_id:    ID of the user.
        session_id: UUID string of the just-completed session.
    """
    st.caption(f"Sesi: {session_id[:8]}…")

    with get_session() as sess:
        raw_feedbacks = get_session_feedback(sess, user_id, session_id)
        summary = get_longitudinal_summary(sess, user_id)
        bias_metric = (
            sess.query(BiasMetric)
            .filter_by(user_id=user_id, session_id=session_id)
            .first()
        )
        metric_data = {
            "ocs": bias_metric.overconfidence_score or 0.0 if bias_metric else 0.0,
            "dei": abs(bias_metric.disposition_dei or 0.0) if bias_metric else 0.0,
            "lai": bias_metric.loss_aversion_index or 0.0 if bias_metric else 0.0,
        }
        # Serialize ORM objects to dicts before session closes
        feedbacks = [
            {
                "bias_type": fb.bias_type,
                "severity": fb.severity,
                "explanation_text": fb.explanation_text or "",
                "recommendation_text": fb.recommendation_text or "",
            }
            for fb in raw_feedbacks
        ]

    if not feedbacks:
        st.warning("Belum ada data umpan balik untuk sesi ini.")
        return

    # --- TL;DR Summary Card ---
    _render_session_results(feedbacks, metric_data, user_id, session_id)

    st.divider()

    # --- Gauge summary strip ---
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

    # Build previous-session severity lookup
    prev_severities: dict[str, str | None] = {}
    if len(summary["sessions"]) >= 2:
        try:
            curr_idx = summary["sessions"].index(session_id)
        except ValueError:
            curr_idx = -1
        if curr_idx > 0:
            for bias_type in summary["trend"]:
                trend_list = summary["trend"][bias_type]
                if curr_idx - 1 < len(trend_list):
                    prev_severities[bias_type] = trend_list[curr_idx - 1]

    st.markdown("## Ringkasan Bias Kognitif")
    st.markdown(
        "Berikut adalah hasil analisis pola keputusan investasi kamu pada sesi ini. "
        "Setiap kartu menunjukkan tingkat kecenderungan bias tertentu beserta saran perbaikan."
    )

    for fb in feedbacks:
        render_bias_card(
            bias_type=fb["bias_type"],
            severity=fb["severity"],
            explanation=fb["explanation_text"],
            recommendation=fb["recommendation_text"],
            prev_severity=prev_severities.get(fb["bias_type"]),
        )

    render_stated_vs_revealed(user_id)

    # Interaction synthesis (teaser before session 5, full narrative after)
    render_interaction_synthesis(user_id, session_id)

    render_anomaly_session_flag(user_id, session_id)

    # --- Session navigation CTAs ---
    st.divider()
    col_new, col_profile = st.columns(2)
    with col_new:
        if st.button("🔄 Mulai Sesi Baru", use_container_width=True, type="primary"):
            st.session_state["current_page"] = "Simulasi Investasi"
            st.rerun()
    with col_profile:
        if st.button("🧠 Lihat Profil Kognitif →", use_container_width=True):
            st.session_state["current_page"] = "Profil Kognitif Saya"
            st.rerun()

    # --- Post-Session Self-Assessment Survey ---
    _render_post_session_survey(user_id=user_id, session_id=session_id)


def render_stated_vs_revealed(user_id: int) -> None:
    """Render the Stated vs. Revealed Behavior comparison panel.

    Shows a color-coded 3-row table comparing what the user reported in their
    pre-simulation survey against what was detected by the bias engine.
    Only displayed when the user has a UserSurvey record.

    Args:
        user_id: ID of the user.
    """
    from modules.analytics.comparison import build_stated_vs_revealed

    with get_session() as sess:
        report = build_stated_vs_revealed(user_id, sess)

    if not report.has_survey:
        st.markdown("---")
        st.info(
            "📝 **Isi survei awal untuk melihat perbandingan pernyataan vs. perilaku Anda di sini.**\n\n"
            "Survei singkat ini memungkinkan sistem membandingkan apa yang Anda nyatakan "
            "tentang kebiasaan trading Anda dengan pola perilaku yang terdeteksi dari simulasi."
        )
        return

    st.markdown("---")
    st.subheader("🔍 Perbandingan: Niat vs Aksi")
    st.caption(
        "Perbandingan ini memakai survei terbaru Anda — baik dari pendaftaran "
        "awal maupun sesi sebelumnya — sehingga bersifat dinamis mengikuti "
        "perkembangan pemahaman diri Anda."
    )

    _LEVEL_ID = {"low": "Rendah", "medium": "Sedang", "high": "Tinggi"}
    _DISC_COLOR = {
        "aligned": "#52C41A",
        "underestimates_bias": "#E8553A",
        "overestimates_discipline": "#F5A623",
        "unable_to_compare": "#78909c",
    }
    _DISC_LABEL = {
        "aligned": "✅ Sesuai",
        "underestimates_bias": "🔴 Meremehkan Bias",
        "overestimates_discipline": "🟠 Melebihkan Bias",
        "unable_to_compare": "— Tidak Dapat Dibandingkan",
    }

    # Header row
    h1, h2, h3, h4 = st.columns([2, 1.5, 1.5, 2])
    h1.markdown("**Bias**")
    h2.markdown("**Yang Anda Nyatakan**")
    h3.markdown("**Yang Terdeteksi**")
    h4.markdown("**Kesenjangan**")
    st.markdown("<hr style='margin:4px 0; border-color:#E5E7EB;'>", unsafe_allow_html=True)

    narratives: list[str] = []
    for comp in report.comparisons:
        c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 2])
        color = _DISC_COLOR.get(comp.discrepancy, "#78909c")
        disc_label = _DISC_LABEL.get(comp.discrepancy, comp.discrepancy)
        c1.markdown(f"**{comp.bias_name}**")
        c2.markdown(_LEVEL_ID.get(comp.stated_level, comp.stated_level))
        c3.markdown(_LEVEL_ID.get(comp.revealed_level, comp.revealed_level))
        c4.markdown(
            f"<span style='color:{color}; font-weight:600;'>{disc_label}</span>",
            unsafe_allow_html=True,
        )
        if comp.interpretation_id:
            narratives.append(comp.interpretation_id)

    # Synthesis paragraph
    if narratives:
        st.markdown("---")
        synthesis = " ".join(narratives)
        if report.overall_alignment == "discrepant":
            st.warning(
                "**Perhatian:** Terdapat kesenjangan antara persepsi diri Anda dan perilaku "
                f"yang terdeteksi. {synthesis}"
            )
        else:
            st.info(
                f"**Ringkasan:** {synthesis}"
            )


def _render_post_session_survey(user_id: int, session_id: str) -> None:
    """Render the post-session self-assessment survey if not yet submitted.

    Shows a 4-question Likert survey capturing self-assessed bias awareness
    and feedback usefulness. Persisted as PostSessionSurvey in the database.
    Idempotent — does not re-render if already submitted for this session.
    """
    from database.models import PostSessionSurvey

    # Check if already submitted for this session
    with get_session() as check_sess:
        already_submitted = (
            check_sess.query(PostSessionSurvey)
            .filter_by(user_id=user_id, session_id=session_id)
            .first()
        ) is not None

    if already_submitted:
        st.caption("✅ Survei evaluasi diri untuk sesi ini sudah diisi. Terima kasih!")
        return

    st.divider()
    with st.expander("📝 Evaluasi Diri: Seberapa Menyadari Kamu Biasmu?", expanded=True):
        st.caption(
            "Jawab pertanyaan berikut berdasarkan perasaanmu **sebelum** melihat hasil "
            "analisis di atas. Jawaban kamu membantu penelitian ini memahami seberapa "
            "efektif umpan balik CDT dalam meningkatkan kesadaran diri investor."
        )

        LIKERT = {
            1: "1 — Tidak menyadari sama sekali",
            2: "2 — Sedikit menyadari",
            3: "3 — Cukup menyadari",
            4: "4 — Menyadari",
            5: "5 — Sangat menyadari",
        }
        USEFULNESS = {
            1: "1 — Tidak berguna",
            2: "2 — Kurang berguna",
            3: "3 — Cukup berguna",
            4: "4 — Berguna",
            5: "5 — Sangat berguna",
        }

        with st.form(f"post_survey_{session_id[:8]}"):
            q_oc = st.select_slider(
                "Seberapa menyadari kamu potensi **overconfidence** (terlalu sering trading) "
                "dalam keputusanmu selama sesi ini?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: LIKERT[x],
            )
            q_dei = st.select_slider(
                "Seberapa menyadari kamu potensi **efek disposisi** (menjual saham untung "
                "terlalu cepat / menahan saham rugi) dalam sesi ini?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: LIKERT[x],
            )
            q_lai = st.select_slider(
                "Seberapa menyadari kamu kecenderungan **loss aversion** (enggan melepas "
                "posisi merugi) yang mungkin memengaruhi keputusanmu?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: LIKERT[x],
            )
            q_use = st.select_slider(
                "Seberapa berguna umpan balik yang kamu terima dari sistem ini?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: USEFULNESS[x],
            )

            submitted = st.form_submit_button(
                "Kirim Evaluasi Diri", use_container_width=True, type="primary"
            )

        if submitted:
            try:
                with get_session() as save_sess:
                    save_sess.add(PostSessionSurvey(
                        user_id=user_id,
                        session_id=session_id,
                        self_overconfidence=q_oc,
                        self_disposition=q_dei,
                        self_loss_aversion=q_lai,
                        feedback_usefulness=q_use,
                    ))
                st.success(
                    "Terima kasih atas evaluasimu! Data ini sangat membantu penelitian. 🙏"
                )
                st.rerun()
            except Exception:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "Failed to save PostSessionSurvey for user=%d session=%s",
                    user_id, session_id,
                )
                st.warning("Gagal menyimpan survei. Silakan coba lagi.")
