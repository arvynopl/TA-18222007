"""
modules/feedback/renderer.py — Streamlit feedback display components.

Functions:
    render_feedback_page       — Full post-session feedback page.
    render_bias_card           — Single bias card with severity badge.
    render_longitudinal_section — Session-over-session comparison strip.
"""

from __future__ import annotations

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


_SEVERITY_ORDER = ["none", "mild", "moderate", "severe"]


def _severity_delta(prev: str, curr: str) -> str:
    """Return a delta string comparing two severity labels (Bahasa Indonesia)."""
    prev_idx = _SEVERITY_ORDER.index(prev) if prev in _SEVERITY_ORDER else 0
    curr_idx = _SEVERITY_ORDER.index(curr) if curr in _SEVERITY_ORDER else 0
    prev_label = _SEVERITY_LABEL.get(prev, prev)
    curr_label = _SEVERITY_LABEL.get(curr, curr)
    if curr_idx < prev_idx:
        return f"Sesi lalu: {prev_label} → Sesi ini: {curr_label} ↓"
    elif curr_idx > prev_idx:
        return f"Sesi lalu: {prev_label} → Sesi ini: {curr_label} ↑"
    return f"Sesi lalu: {prev_label} → Sesi ini: {curr_label} (tetap)"


def render_bias_card(bias_type: str, severity: str, explanation: str, recommendation: str, prev_severity: str | None = None) -> None:
    """Render a single bias feedback card with colour-coded severity badge.

    Args:
        bias_type:      e.g. "disposition_effect".
        severity:       "none", "mild", "moderate", or "severe".
        explanation:    Explanation text (Bahasa Indonesia).
        recommendation: Recommendation text (Bahasa Indonesia).
        prev_severity:  Severity from the previous session, if available.
    """
    icon = _SEVERITY_COLOUR.get(severity, "⚪")
    label = _SEVERITY_LABEL.get(severity, severity.capitalize())
    title = _BIAS_DISPLAY_NAME.get(bias_type, bias_type.replace("_", " ").title())

    with st.expander(f"{icon} {title} — {label}", expanded=(severity != "none")):
        # Enhancement 6: show delta vs previous session if available
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
        summary = get_longitudinal_summary(sess, user_id)

    if not feedbacks:
        st.warning("Belum ada data umpan balik untuk sesi ini.")
        return

    # Build previous-session severity lookup (Enhancement 6)
    prev_severities: dict[str, str | None] = {}
    if len(summary["sessions"]) >= 2:
        # Find index of current session in history
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
            bias_type=fb.bias_type,
            severity=fb.severity,
            explanation=fb.explanation_text or "",
            recommendation=fb.recommendation_text or "",
            prev_severity=prev_severities.get(fb.bias_type),
        )

    render_longitudinal_section(user_id)

    st.markdown("---")
    if st.button("Lihat Profil Kognitif Saya →", use_container_width=True):
        st.session_state["current_page"] = "Profil Kognitif Saya"
        st.rerun()
