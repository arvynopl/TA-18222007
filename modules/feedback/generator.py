"""
modules/feedback/generator.py — Rule-based feedback generation.

Combines bias metrics + templates into FeedbackHistory records.

Functions:
    generate_feedback       — Create and persist FeedbackHistory for a session.
    compute_counterfactual  — Estimate gains if user had held a winning position longer.
    get_session_feedback    — Retrieve delivered feedback for a session.
    get_longitudinal_summary — Summarise bias trends across all sessions.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from config import (
    DEI_MODERATE, DEI_SEVERE,
    LAI_MODERATE, LAI_SEVERE,
    OCS_MODERATE, OCS_SEVERE,
)
from database.models import BiasMetric, CognitiveProfile, FeedbackHistory, MarketSnapshot
from modules.analytics.bias_metrics import classify_severity
from modules.feedback.templates import TEMPLATES


def compute_counterfactual(
    db_session: Session,
    realized_trades: list[dict],
    open_positions: list[dict],
    session_snapshots: dict,
    extra_rounds: int = 3,
) -> str:
    """Estimate what the user would have earned by holding the best winner longer.

    Finds the realized trade with the highest sell value, then looks up what the
    price would have been *extra_rounds* later (if available).

    Args:
        db_session:        Active SQLAlchemy session.
        realized_trades:   From SessionFeatures.realized_trades.
        open_positions:    From SessionFeatures.open_positions.
        session_snapshots: Dict mapping snapshot_id → close price (not used directly).
        extra_rounds:      How many additional rounds to project forward.

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
    target_round = best["sell_round"] + extra_rounds
    if target_round > 14:
        return ""

    # We don't have a direct round→snapshot mapping here; use a heuristic estimate
    # Assume linear extrapolation from buy→sell trend (conservative)
    trend_per_round = (best["sell_price"] - best["buy_price"]) / max(
        best["sell_round"] - best["buy_round"], 1
    )
    projected_price = best["sell_price"] + trend_per_round * extra_rounds
    projected_gain = (projected_price - best["buy_price"]) * best["quantity"]

    if projected_gain <= actual_gain:
        return ""

    additional = projected_gain - actual_gain
    return (
        f"Contoh: kamu menjual {best['stock_id']} di putaran {best['sell_round']} "
        f"dengan keuntungan Rp {actual_gain:,.0f}. "
        f"Jika kamu menahan {extra_rounds} putaran lebih lama, "
        f"estimasi keuntungan bisa mencapai Rp {projected_gain:,.0f} "
        f"(tambahan ≈ Rp {additional:,.0f})."
    )


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

    trade_count = (
        (bias_metric.overconfidence_score and 1 or 0)
    )  # placeholder — computed below from template slot

    win_count = sum(1 for t in realized_trades if t["sell_price"] > t["buy_price"])
    loss_count = sum(1 for t in realized_trades if t["sell_price"] < t["buy_price"])
    buy_sell_count = len([
        t for t in realized_trades
    ]) + win_count + loss_count  # approximation

    # Better: use the raw counts from the feature extraction; fall back to 0
    # The caller should pass these if available
    total_trades = len(realized_trades) + len(open_positions)

    # Counterfactual text (only for severe cases)
    counterfactual_disp = compute_counterfactual(
        db_session, realized_trades, open_positions, {}
    )
    counterfactual_oc = (
        f"Dengan mengurangi frekuensi trading, kamu bisa menghemat lebih banyak modal "
        f"untuk peluang yang benar-benar menjanjikan."
        if (bias_metric.overconfidence_score or 0) >= OCS_SEVERE else ""
    )
    counterfactual_la = (
        f"Posisi merugi yang kamu pertahankan mengunci modal yang bisa digunakan "
        f"untuk peluang investasi lainnya."
        if (bias_metric.loss_aversion_index or 0) >= LAI_SEVERE else ""
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
            "slots": {
                "ocs": ocs_val,
                "trade_count": len(realized_trades) * 2,  # approx buy+sell
                "counterfactual_text": counterfactual_oc,
            },
        },
        {
            "bias_type": "loss_aversion",
            "value": lai_val,
            "severe_t": LAI_SEVERE,
            "moderate_t": LAI_MODERATE,
            "slots": {
                "lai": lai_val,
                "counterfactual_text": counterfactual_la,
            },
        },
    ]

    records: list[FeedbackHistory] = []
    for cfg in bias_configs:
        severity = classify_severity(cfg["value"], cfg["severe_t"], cfg["moderate_t"])

        if severity == "none":
            explanation = (
                f"Tidak terdeteksi bias {cfg['bias_type'].replace('_', ' ')} yang "
                f"signifikan pada sesi ini. Pertahankan pola pengambilan keputusan "
                f"yang baik ini!"
            )
            recommendation = "Terus pantau keputusan investasimu dan jaga konsistensi."
        else:
            tmpl = TEMPLATES[cfg["bias_type"]][severity]
            try:
                explanation = tmpl["explanation"].format(**cfg["slots"])
                recommendation = tmpl["recommendation"].format(**cfg["slots"])
            except KeyError:
                explanation = tmpl["explanation"]
                recommendation = tmpl["recommendation"]

        record = FeedbackHistory(
            user_id=user_id,
            session_id=session_id,
            bias_type=cfg["bias_type"],
            severity=severity,
            explanation_text=explanation,
            recommendation_text=recommendation,
            delivered_at=datetime.utcnow(),
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
