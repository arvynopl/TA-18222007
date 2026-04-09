"""
modules/feedback/generator.py — Rule-based feedback generation.

Combines bias metrics + templates into FeedbackHistory records.

Functions:
    generate_feedback       — Create and persist FeedbackHistory for a session.
    compute_counterfactual  — Estimate gains if user had held a winning position longer.
    get_session_feedback    — Retrieve delivered feedback for a session.
    get_longitudinal_summary — Summarise bias trends across all sessions.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

import logging

from config import (
    CDT_MODIFIER_STABILITY_THRESHOLD,
    DEI_MILD, DEI_MODERATE, DEI_SEVERE,
    LAI_MILD, LAI_MODERATE, LAI_SEVERE,
    MIN_TRADES_FOR_FULL_SEVERITY,
    OCS_MILD, OCS_MODERATE, OCS_SEVERE,
    ROUNDS_PER_SESSION,
)

logger = logging.getLogger(__name__)
from database.models import BiasMetric, CognitiveProfile, FeedbackHistory, MarketSnapshot, UserAction
from modules.analytics.bias_metrics import classify_severity
from modules.feedback.templates import TEMPLATES


def compute_counterfactual(
    db_session: Session,
    realized_trades: list[dict],
    open_positions: list[dict],
    session_snapshots: dict | None = None,
    extra_rounds: int = 3,
    session_id: str | None = None,
) -> str:
    """Estimate what the user would have earned by holding the best winner longer.

    Finds the realized trade with the highest sell value, then looks up what the
    price would have been *extra_rounds* later (if available).

    Args:
        db_session:        Active SQLAlchemy session.
        realized_trades:   From SessionFeatures.realized_trades.
        open_positions:    From SessionFeatures.open_positions.
        session_snapshots: Deprecated, unused. Pass None.
        extra_rounds:      How many additional rounds to project forward.
        session_id:        Optional session UUID. When provided, actual MarketSnapshot
                           data is used for projection instead of linear extrapolation
                           (preferred).

    Returns:
        A Bahasa Indonesia counterfactual string, or empty string if not applicable.
    """
    # Find winner with highest absolute gain
    winners = [
        t for t in realized_trades if t["sell_price"] > t["buy_price"]
    ]
    if not winners:
        return ""

    best = max(winners, key=lambda t: (t["sell_price"] - t["buy_price"]) * t["quantity"])
    actual_gain = (best["sell_price"] - best["buy_price"]) * best["quantity"]

    # Try to find what price was extra_rounds after sell_round
    # Clamp extra_rounds so we don't project beyond the simulation window
    actual_extra = min(extra_rounds, ROUNDS_PER_SESSION - best["sell_round"])
    if actual_extra <= 0:
        return ""
    target_round = best["sell_round"] + actual_extra

    # Prefer actual market data over linear extrapolation.
    # If session_id is provided, look up the real MarketSnapshot price for
    # the target round by querying the UserAction record for that round.
    projected_price: float | None = None
    if session_id is not None:
        target_action = (
            db_session.query(UserAction)
            .filter_by(
                session_id=session_id,
                stock_id=best["stock_id"],
                scenario_round=target_round,
            )
            .first()
        )
        if target_action:
            snap = db_session.get(MarketSnapshot, target_action.snapshot_id)
            if snap and snap.close is not None:
                projected_price = snap.close

    if projected_price is None:
        # Fallback: linear extrapolation with a price floor to prevent negatives.
        trend_per_round = (best["sell_price"] - best["buy_price"]) / max(
            best["sell_round"] - best["buy_round"], 1
        )
        projected_price = max(best["sell_price"] + trend_per_round * actual_extra, 0.01)

    projected_gain = (projected_price - best["buy_price"]) * best["quantity"]

    if projected_gain <= actual_gain:
        return ""

    additional = projected_gain - actual_gain
    return (
        f"Contoh: kamu menjual {best['stock_id']} di putaran {best['sell_round']} "
        f"dengan keuntungan Rp {actual_gain:,.0f}. "
        f"Jika kamu menahan {actual_extra} putaran lebih lama, "
        f"estimasi keuntungan bisa mencapai Rp {projected_gain:,.0f} "
        f"(tambahan ≈ Rp {additional:,.0f})."
    )


_SEVERITY_RANK: dict[str, int] = {"none": 0, "mild": 1, "moderate": 2, "severe": 3}


def _get_cdt_modifier(
    db_session: Session,
    user_id: int,
    session_id: str,
    bias_type: str,
    current_severity: str,
    profile: CognitiveProfile,
) -> str:
    """Generate a CDT-aware contextual sentence appended to feedback explanation.

    Returns an empty string when:
      - Fewer than 3 sessions have been completed (insufficient longitudinal data)
      - No notable trend or stability pattern is detected

    Args:
        db_session:       Active SQLAlchemy session.
        user_id:          ID of the user.
        session_id:       Current session UUID (excluded from previous-feedback lookup).
        bias_type:        One of "overconfidence", "disposition_effect", "loss_aversion".
        current_severity: Severity label for this session.
        profile:          Current CognitiveProfile.

    Returns:
        A Bahasa Indonesia modifier string, or "".
    """
    if profile.session_count < 3:
        return ""

    curr_rank = _SEVERITY_RANK.get(current_severity, 0)
    modifiers: list[str] = []

    # Trend vs. previous session
    prev_feedback = (
        db_session.query(FeedbackHistory)
        .filter_by(user_id=user_id, bias_type=bias_type)
        .filter(FeedbackHistory.session_id != session_id)
        .order_by(FeedbackHistory.delivered_at.desc())
        .first()
    )

    if prev_feedback:
        prev_rank = _SEVERITY_RANK.get(prev_feedback.severity, 0)
        if curr_rank < prev_rank and current_severity != "none":
            modifiers.append(
                "Perkembangan positif: kecenderungan bias ini menurun dibanding sesi sebelumnya."
            )
        elif curr_rank > prev_rank:
            modifiers.append(
                "Perhatian: intensitas bias ini meningkat dari sesi sebelumnya."
            )

    # Persistent-pattern warning for stable but elevated bias
    if (
        profile.stability_index > CDT_MODIFIER_STABILITY_THRESHOLD
        and current_severity in ("moderate", "severe")
    ):
        modifiers.append(
            "Pola ini terdeteksi konsisten di beberapa sesi terakhir — "
            "pertimbangkan untuk mengubah strategi tradingmu secara lebih mendasar."
        )

    return " ".join(modifiers)


def generate_feedback(
    db_session: Session,
    user_id: int,
    session_id: str,
    bias_metric: BiasMetric,
    profile: CognitiveProfile,
    realized_trades: list[dict] | None = None,
    open_positions: list[dict] | None = None,
) -> list[FeedbackHistory]:
    """Generate and persist FeedbackHistory records for a completed session.

    One FeedbackHistory row is created per bias type (always 3 rows, even for
    severity="none", so the renderer can display a green "no bias" card).

    Args:
        db_session:      Active SQLAlchemy session.
        user_id:         ID of the user.
        session_id:      UUID string of the session.
        bias_metric:     Computed BiasMetric for this session.
        profile:         Current CognitiveProfile.
        realized_trades: Optional list from SessionFeatures (for counterfactual).
        open_positions:  Optional list from SessionFeatures (for counterfactual).

    Returns:
        List of 3 persisted FeedbackHistory instances.
    """
    realized_trades = realized_trades or []
    open_positions = open_positions or []

    # Actual buy+sell action count from DB (Bug 2 fix)
    trade_count = (
        db_session.query(UserAction)
        .filter_by(user_id=user_id, session_id=session_id)
        .filter(UserAction.action_type.in_(["buy", "sell"]))
        .count()
    )

    has_trades = (
        bool(realized_trades)
        or bool(open_positions)
        or trade_count > 0
        or (bias_metric.overconfidence_score or 0) > 1e-9
        or (bias_metric.loss_aversion_index or 0) > 1e-9
    )

    win_count = sum(1 for t in realized_trades if t["sell_price"] > t["buy_price"])
    loss_count = sum(1 for t in realized_trades if t["sell_price"] < t["buy_price"])

    # Pre-compute severities so counterfactuals are only generated when needed
    dei_val_abs = abs(bias_metric.disposition_dei or 0.0)
    dei_severity_pre = classify_severity(dei_val_abs, DEI_SEVERE, DEI_MODERATE, DEI_MILD)
    ocs_val_pre = bias_metric.overconfidence_score or 0.0
    lai_val_pre = bias_metric.loss_aversion_index or 0.0

    # Counterfactual text — only computed for severe cases to avoid wasted work
    counterfactual_disp = (
        compute_counterfactual(
            db_session, realized_trades, open_positions,
            session_id=session_id,
        )
        if dei_severity_pre == "severe"
        else ""
    )
    counterfactual_oc = (
        f"Dengan mengurangi frekuensi trading, kamu bisa menghemat lebih banyak modal "
        f"untuk peluang yang benar-benar menjanjikan."
        if ocs_val_pre >= OCS_SEVERE else ""
    )
    counterfactual_la = (
        f"Posisi merugi yang kamu pertahankan mengunci modal yang bisa digunakan "
        f"untuk peluang investasi lainnya."
        if lai_val_pre >= LAI_SEVERE else ""
    )

    # Slot values
    dei_val = bias_metric.disposition_dei or 0.0
    pgr_val = bias_metric.disposition_pgr or 0.0
    plr_val = bias_metric.disposition_plr or 0.0
    ocs_val = bias_metric.overconfidence_score or 0.0
    lai_val = bias_metric.loss_aversion_index or 0.0

    bias_configs = [
        {
            "bias_type": "disposition_effect",
            "value": abs(dei_val),
            "severe_t": DEI_SEVERE,
            "moderate_t": DEI_MODERATE,
            "mild_t": DEI_MILD,
            "min_sample_met": len(realized_trades) >= MIN_TRADES_FOR_FULL_SEVERITY,
            "slots": {
                "dei": dei_val,
                "pgr": pgr_val,
                "plr": plr_val,
                "win_count": win_count,
                "loss_count": loss_count,
                "counterfactual_text": counterfactual_disp,
            },
        },
        {
            "bias_type": "overconfidence",
            "value": ocs_val,
            "severe_t": OCS_SEVERE,
            "moderate_t": OCS_MODERATE,
            "mild_t": OCS_MILD,
            "slots": {
                "ocs": ocs_val,
                "trade_count": trade_count,
                "counterfactual_text": counterfactual_oc,
            },
        },
        {
            "bias_type": "loss_aversion",
            "value": lai_val,
            "severe_t": LAI_SEVERE,
            "moderate_t": LAI_MODERATE,
            "mild_t": LAI_MILD,
            "min_sample_met": len(realized_trades) >= MIN_TRADES_FOR_FULL_SEVERITY,
            "slots": {
                "lai": lai_val,
                "counterfactual_text": counterfactual_la,
            },
        },
    ]

    records: list[FeedbackHistory] = []
    for cfg in bias_configs:
        severity = classify_severity(
            cfg["value"],
            cfg["severe_t"],
            cfg["moderate_t"],
            cfg.get("mild_t"),
            min_sample_met=cfg.get("min_sample_met", True),
        )
        logger.debug("bias=%s value=%.3f severity=%s", cfg["bias_type"], cfg["value"], severity)

        if not has_trades:
            severity = "none"
            explanation = (
                f"Data transaksi tidak cukup untuk menganalisis "
                f"{cfg['bias_type'].replace('_', ' ')} pada sesi ini. "
                f"Cobalah untuk melakukan beberapa transaksi beli dan jual "
                f"pada sesi berikutnya agar sistem dapat mengevaluasi pola keputusanmu."
            )
            recommendation = (
                "Lakukan setidaknya beberapa transaksi beli dan jual pada sesi berikutnya "
                "untuk memungkinkan analisis bias yang bermakna."
            )
        elif severity == "none":
            explanation = (
                f"Tidak terdeteksi bias {cfg['bias_type'].replace('_', ' ')} yang "
                f"signifikan pada sesi ini. Pertahankan pola pengambilan keputusan "
                f"yang baik ini!"
            )
            recommendation = "Terus pantau keputusan investasimu dan jaga konsistensi."
        else:
            tmpl = TEMPLATES[cfg["bias_type"]][severity]
            # Use defaultdict so missing slots become empty strings (Bug 7 fix)
            safe_slots = defaultdict(str, cfg["slots"])
            explanation = tmpl["explanation"].format_map(safe_slots)
            recommendation = tmpl["recommendation"].format_map(safe_slots)

        # Append CDT-aware longitudinal modifier when applicable
        if has_trades and severity != "none":
            cdt_mod = _get_cdt_modifier(
                db_session, user_id, session_id, cfg["bias_type"], severity, profile
            )
            if cdt_mod:
                explanation = explanation + " " + cdt_mod

        record = FeedbackHistory(
            user_id=user_id,
            session_id=session_id,
            bias_type=cfg["bias_type"],
            severity=severity,
            explanation_text=explanation,
            recommendation_text=recommendation,
            delivered_at=datetime.now(timezone.utc),
        )
        db_session.add(record)
        records.append(record)

    db_session.flush()
    return records


def get_session_feedback(
    db_session: Session, user_id: int, session_id: str
) -> list[FeedbackHistory]:
    """Retrieve all FeedbackHistory records for a specific session.

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user.
        session_id: UUID string of the session.

    Returns:
        List of FeedbackHistory instances.
    """
    return (
        db_session.query(FeedbackHistory)
        .filter_by(user_id=user_id, session_id=session_id)
        .order_by(FeedbackHistory.delivered_at)
        .all()
    )


def get_longitudinal_summary(db_session: Session, user_id: int) -> dict:
    """Summarise bias severity trends across all sessions for a user.

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user.

    Returns:
        Dict with keys: sessions (list of session_id), trend (dict of bias_type →
        list of severity labels per session), latest (dict of bias_type → severity).
    """
    all_feedback = (
        db_session.query(FeedbackHistory)
        .filter_by(user_id=user_id)
        .order_by(FeedbackHistory.delivered_at)
        .all()
    )

    sessions_ordered: list[str] = []
    seen: set[str] = set()
    for f in all_feedback:
        if f.session_id not in seen:
            sessions_ordered.append(f.session_id)
            seen.add(f.session_id)

    trend: dict[str, list[str]] = {
        "disposition_effect": [],
        "overconfidence": [],
        "loss_aversion": [],
    }
    for sid in sessions_ordered:
        session_fb = [f for f in all_feedback if f.session_id == sid]
        for bias_type in trend:
            match = next((f for f in session_fb if f.bias_type == bias_type), None)
            trend[bias_type].append(match.severity if match else "none")

    latest = {
        bias_type: trend[bias_type][-1] if trend[bias_type] else "none"
        for bias_type in trend
    }

    return {"sessions": sessions_ordered, "trend": trend, "latest": latest}
