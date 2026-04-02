"""
modules/feedback/renderer.py — Streamlit feedback display components.

Functions:
    render_feedback_page       — Full post-session feedback page.
    render_bias_card           — Single bias card with severity badge.
    render_longitudinal_section — Session-over-session comparison strip.
"""

import streamlit as st

from database.connection import get_session
from modules.analytics.bias_metrics import classify_severity
from modules.feedback.generator import get_longitudinal_summary, get_session_feedback

# Severity → display colour (using Streamlit markdown colour syntax)
_SEVERITY_COLOUR = {
    "severe": "🔴",
    "moderate": "🟠",
    "mild": "🟡",
    "none": "🟢",
}

_SEVERITY_LABEL = {
    "severe": "Berat",
    "moderate": "Sedang",
    "mild": "Ringan",
    "none": "Tidak Terdeteksi",
}

_BIAS_DISPLAY_NAME = {
    "disposition_effect": "Efek Disposisi",
    "overconfidence": "Overconfidence",
    "loss_aversion": "Aversion terhadap Kerugian",
}


def render_bias_card(bias_type: str, severity: str, explanation: str, recommendation: str) -> None:
    """Render a single bias feedback card with colour-coded severity badge.

    Args:
        bias_type:      e.g. "disposition_effect".
        severity:       "none", "mild", "moderate", or "severe".
        explanation:    Explanation text (Bahasa Indonesia).
        recommendation: Recommendation text (Bahasa Indonesia).
    """
    icon = _SEVERITY_COLOUR.get(severity, "⚪")
    label = _SEVERITY_LABEL.get(severity, severity.capitalize())
    title = _BIAS_DISPLAY_NAME.get(bias_type, bias_type.replace("_", " ").title())

    with st.expander(f"{icon} {title} — {label}", expanded=(severity != "none")):
        if severity == "none":
            st.success(explanation)
        else:
            st.markdown("**Penjelasan:**")
            st.info(explanation)
            st.markdown("**Rekomendasi:**")
            st.warning(recommendation)


def render_longitudinal_section(user_id: int) -> None:
    """Show session-over-session severity history as a compact table.

    Args:
        user_id: ID of the user.
    """
    with get_session() as sess:
        summary = get_longitudinal_summary(sess, user_id)

    if len(summary["sessions"]) < 2:
        return

    st.markdown("---")
    st.subheader("Perbandingan Antar Sesi")

    rows = []
    for i, sid in enumerate(summary["sessions"], start=1):
        row = {"Sesi": f"Sesi {i}"}
        for bias_type in ["disposition_effect", "overconfidence", "loss_aversion"]:
            sev = summary["trend"][bias_type][i - 1] if i - 1 < len(summary["trend"][bias_type]) else "none"
            icon = _SEVERITY_COLOUR.get(sev, "⚪")
            row[_BIAS_DISPLAY_NAME[bias_type]] = f"{icon} {_SEVERITY_LABEL.get(sev, sev)}"
        rows.append(row)

    st.table(rows)


def render_feedback_page(user_id: int, session_id: str) -> None:
    """Render the complete post-session feedback page.

    Args:
        user_id:    ID of the user.
        session_id: UUID string of the just-completed session.
    """
    st.title("Hasil Analisis & Umpan Balik")
    st.caption(f"Sesi: {session_id[:8]}…")

    with get_session() as sess:
        feedbacks = get_session_feedback(sess, user_id, session_id)

    if not feedbacks:
        st.warning("Belum ada data umpan balik untuk sesi ini.")
        return

    st.markdown("## Ringkasan Bias Kognitif")
    st.markdown(
        "Berikut adalah hasil analisis pola keputusan investasi kamu pada sesi ini. "
        "Setiap kartu menunjukkan tingkat kecenderungan bias tertentu beserta saran perbaikan."
    )

    for fb in feedbacks:
        render_bias_card(
            bias_type=fb.bias_type,
            severity=fb.severity,
            explanation=fb.explanation_text or "",
            recommendation=fb.recommendation_text or "",
        )

    render_longitudinal_section(user_id)

    st.markdown("---")
    if st.button("Lihat Profil Kognitif Saya →", use_container_width=True):
        st.session_state["current_page"] = "Profil Kognitif Saya"
        st.rerun()
