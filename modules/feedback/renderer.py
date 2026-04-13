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
from modules.feedback.generator import get_longitudinal_summary, get_session_feedback
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
    color = SEVERITY_COLORS.get(severity, "#78909c")
    bg = SEVERITY_BG.get(severity, "rgba(255,255,255,0.05)")
    icon = SEVERITY_ICONS.get(severity, "⚪")
    label = SEVERITY_LABELS.get(severity, severity)
    title = BIAS_NAMES.get(bias_type, bias_type.replace("_", " ").title())
    desc = BIAS_DESCRIPTIONS.get(bias_type, "")

    # Styled card header with colored left border
    st.markdown(
        f"""
        <div style="
            border-left: 4px solid {color};
            background: {bg};
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 4px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-size: 17px; font-weight: 600; color: white;">
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
            <p style="color: #90A4AE; font-size: 12px; margin: 0;">{desc}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Expander for detail content (expanded for non-none severity)
    with st.expander(f"{icon} {title} — {label}", expanded=(severity != "none")):
        if prev_severity is not None:
            delta_str = _severity_delta(prev_severity, severity)
            st.caption(delta_str)

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


def render_interaction_synthesis(user_id: int, session_id: str) -> None:
    """Render a coupled-bias synthesis card when strong interactions are detected.

    Reads CognitiveProfile.interaction_scores (already stored) and calls
    _get_interaction_modifier() from the generator. Only renders when at least
    one pairwise Pearson r exceeds the threshold AND session_count >= 5.

    Args:
        user_id:    ID of the user.
        session_id: UUID of the current session (unused directly; passed for
                    future extensibility).
    """
    from database.models import CognitiveProfile
    from modules.feedback.generator import _get_interaction_modifier

    with get_session() as sess:
        profile = sess.query(CognitiveProfile).filter_by(user_id=user_id).first()
        if profile is None:
            return
        # Snapshot relevant fields before session closes
        session_count = profile.session_count
        interaction_scores = profile.interaction_scores
        stability_index = profile.stability_index

    # Build a temporary profile-like namespace for the modifier function
    # (avoids DetachedInstanceError — all data already extracted above)
    class _ProfileSnapshot:
        pass

    snap = _ProfileSnapshot()
    snap.session_count = session_count
    snap.interaction_scores = interaction_scores
    snap.stability_index = stability_index

    insights = _get_interaction_modifier(snap)  # type: ignore[arg-type]
    if not insights:
        return

    st.markdown("---")
    st.subheader("🔗 Pola Bias Gabungan")
    st.caption(
        "Analisis keterkaitan antar-bias berdasarkan riwayat multi-sesi kamu. "
        "Pola ini terdeteksi hanya setelah minimal 5 sesi selesai."
    )

    for insight in insights:
        st.info(insight)


def render_feedback_page(user_id: int, session_id: str) -> None:
    """Render the complete post-session feedback page.

    Args:
        user_id:    ID of the user.
        session_id: UUID string of the just-completed session.
    """
    st.title("Hasil Analisis & Umpan Balik")
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

    render_longitudinal_section(user_id)

    render_interaction_synthesis(user_id=user_id, session_id=session_id)

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
