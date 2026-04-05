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

    st.markdown(
        f"""
        <div style="
            border-left: 4px solid {color};
            background: {bg};
            border-radius: 8px;
            padding: 20px 24px;
            margin-bottom: 16px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 18px; font-weight: 600; color: white;">
                    {icon} {title}
                </span>
                <span style="
                    background: {color}22;
                    color: {color};
                    padding: 4px 12px;
                    border-radius: 12px;
                    font-size: 13px;
                    font-weight: 500;
                ">{label}</span>
            </div>
            <p style="color: #90A4AE; font-size: 13px; margin-bottom: 0;">{desc}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if prev_severity is not None:
        delta_str = _severity_delta(prev_severity, severity)
        st.caption(delta_str)

    if severity == "none":
        st.success(explanation)
    else:
        tab_exp, tab_rec = st.tabs(["📖 Penjelasan", "💡 Rekomendasi"])
        with tab_exp:
            st.markdown(explanation)
        with tab_rec:
            st.markdown(recommendation)


def render_longitudinal_section(user_id: int) -> None:
    """Show session-over-session severity history as a colour-coded visual timeline.

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

    n_sessions = len(summary["sessions"])
    for bias_type in ["disposition_effect", "overconfidence", "loss_aversion"]:
        title = BIAS_NAMES.get(bias_type, bias_type)
        st.markdown(f"**{title}**")
        cols = st.columns(min(n_sessions, 8))
        trend = summary["trend"].get(bias_type, [])
        for i, col in enumerate(cols):
            if i < len(trend):
                sev = trend[i]
                color = SEVERITY_COLORS.get(sev, "#78909c")
                label = SEVERITY_LABELS.get(sev, sev)
                col.markdown(
                    f"<div style='text-align:center; padding:8px; "
                    f"border-radius:8px; background:{color}22; "
                    f"border: 1px solid {color}44;'>"
                    f"<div style='font-size:11px; color:#90A4AE;'>Sesi {i + 1}</div>"
                    f"<div style='font-size:13px; color:{color}; font-weight:600;'>{label}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


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
    with g2:
        sev = classify_severity(metric_data["dei"], DEI_SEVERE, DEI_MODERATE, DEI_MILD)
        fig = build_severity_gauge(metric_data["dei"], 1.0, "Efek Disposisi", sev)
        st.plotly_chart(fig, use_container_width=True)
    with g3:
        sev = classify_severity(metric_data["lai"], LAI_SEVERE, LAI_MODERATE, LAI_MILD)
        fig = build_severity_gauge(metric_data["lai"], 3.0, "Loss Aversion", sev)
        st.plotly_chart(fig, use_container_width=True)

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

    st.markdown("---")
    if st.button("Lihat Profil Kognitif Saya →", use_container_width=True):
        st.session_state["current_page"] = "Profil Kognitif Saya"
        st.rerun()
