"""
modules/analytics/bias_metrics.py — Core behavioral bias formulas.

References:
    Odean, T. (1998). Are Investors Reluctant to Realize Their Losses?
        Journal of Finance, 53(5), 1775–1798.
    Barber, B. M., & Odean, T. (2000). Trading Is Hazardous to Your Wealth.
        Journal of Finance, 55(2), 773–806.
    Kahneman, D., & Tversky, A. (1979). Prospect Theory.
        Econometrica, 47(2), 263–291.

Public functions:
    compute_disposition_effect   → (pgr, plr, dei)
    compute_overconfidence_score → float
    compute_loss_aversion_index  → float
    classify_severity            → str
    compute_and_save_metrics     → BiasMetric
"""

import math
from datetime import datetime
from statistics import mean, stdev

from sqlalchemy.orm import Session

from config import (
    DEI_MODERATE, DEI_SEVERE,
    LAI_MODERATE, LAI_SEVERE,
    OCS_MODERATE, OCS_SEVERE,
    ROUNDS_PER_SESSION,
)
from database.models import BiasMetric
from modules.analytics.features import SessionFeatures, extract_session_features


# ---------------------------------------------------------------------------
# Disposition Effect Index (DEI)  — Odean (1998)
# ---------------------------------------------------------------------------

def compute_disposition_effect(
    features: SessionFeatures,
) -> tuple[float, float, float]:
    """Compute PGR, PLR, and DEI from session features.

    DEI measures the tendency to sell winners too early and hold losers too long.

    PGR = Realized_Gains / (Realized_Gains + Paper_Gains)
    PLR = Realized_Losses / (Realized_Losses + Paper_Losses)
    DEI = PGR - PLR

    A positive DEI indicates the disposition effect (Odean, 1998).
    DEI ∈ [−1, 1]; uninflated baseline is near 0.

    Args:
        features: Extracted session features.

    Returns:
        Tuple (pgr, plr, dei). Returns (0.0, 0.0, 0.0) if no trades exist.
    """
    realized_gains = sum(
        1
        for t in features.realized_trades
        if t["sell_price"] > t["buy_price"]
    )
    realized_losses = sum(
        1
        for t in features.realized_trades
        if t["sell_price"] < t["buy_price"]
    )
    paper_gains = sum(
        1
        for p in features.open_positions
        if p["final_price"] > p["avg_price"]
    )
    paper_losses = sum(
        1
        for p in features.open_positions
        if p["final_price"] < p["avg_price"]
    )

    pgr_denom = realized_gains + paper_gains
    plr_denom = realized_losses + paper_losses

    pgr = realized_gains / pgr_denom if pgr_denom > 0 else 0.0
    plr = realized_losses / plr_denom if plr_denom > 0 else 0.0
    dei = pgr - plr

    return pgr, plr, dei


# ---------------------------------------------------------------------------
# Overconfidence Score (OCS)  — Barber & Odean (2000)
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    """Standard sigmoid function: 1 / (1 + e^(-x))."""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def compute_overconfidence_score(features: SessionFeatures) -> float:
    """Compute the Overconfidence Score (OCS) for a session.

    High trading frequency combined with poor performance signals overconfidence
    (Barber & Odean, 2000).

    trade_frequency    = (buy_count + sell_count) / ROUNDS_PER_SESSION
    performance_ratio  = final_value / initial_value
    OCS                = sigmoid(trade_frequency × (1 / max(performance_ratio, 0.01)))

    OCS ∈ [0, 1]; higher = more overconfident.

    Args:
        features: Extracted session features.

    Returns:
        Float in [0, 1].
    """
    trade_frequency = (features.buy_count + features.sell_count) / ROUNDS_PER_SESSION
    performance_ratio = features.final_value / max(features.initial_value, 1.0)
    raw = trade_frequency * (1.0 / max(performance_ratio, 0.01))
    return _sigmoid(raw)


# ---------------------------------------------------------------------------
# Loss Aversion Index (LAI)  — Kahneman & Tversky (1979)
# ---------------------------------------------------------------------------

def compute_loss_aversion_index(features: SessionFeatures) -> float:
    """Compute the Loss Aversion Index (LAI) for a session.

    Measures whether users hold losing positions longer than winning ones,
    consistent with loss aversion (Kahneman & Tversky, 1979).

    avg_hold_losers  = mean holding period (rounds) for stocks sold at a loss
    avg_hold_winners = mean holding period (rounds) for stocks sold at a gain
    LAI              = avg_hold_losers / max(avg_hold_winners, 1)

    LAI > 1 indicates holding losers longer; LAI ≫ 1 indicates strong aversion.

    Args:
        features: Extracted session features.

    Returns:
        Float ≥ 0; returns 1.0 if there are no completed sell trades.
    """
    loser_holds = [
        t["sell_round"] - t["buy_round"]
        for t in features.realized_trades
        if t["sell_price"] < t["buy_price"]
    ]
    winner_holds = [
        t["sell_round"] - t["buy_round"]
        for t in features.realized_trades
        if t["sell_price"] > t["buy_price"]
    ]

    avg_losers = mean(loser_holds) if loser_holds else 0.0
    avg_winners = mean(winner_holds) if winner_holds else 0.0

    return avg_losers / max(avg_winners, 1.0)


# ---------------------------------------------------------------------------
# Severity classifier
# ---------------------------------------------------------------------------

def classify_severity(
    value: float, severe_threshold: float, moderate_threshold: float
) -> str:
    """Map a metric value to a severity label.

    Args:
        value:              The computed metric value.
        severe_threshold:   Value at or above which severity = "severe".
        moderate_threshold: Value at or above which severity = "moderate".

    Returns:
        "severe", "moderate", or "none".
    """
    if value >= severe_threshold:
        return "severe"
    if value >= moderate_threshold:
        return "moderate"
    return "none"


# ---------------------------------------------------------------------------
# Orchestrator: compute all metrics and persist
# ---------------------------------------------------------------------------

def compute_and_save_metrics(
    db_session: Session, user_id: int, session_id: str
) -> BiasMetric:
    """Extract session features, compute all bias metrics, and save to DB.

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user whose session to analyse.
        session_id: UUID string of the completed session.

    Returns:
        The persisted BiasMetric ORM instance.
    """
    features = extract_session_features(db_session, user_id, session_id)

    pgr, plr, dei = compute_disposition_effect(features)
    ocs = compute_overconfidence_score(features)
    lai = compute_loss_aversion_index(features)

    metric = BiasMetric(
        user_id=user_id,
        session_id=session_id,
        overconfidence_score=ocs,
        disposition_pgr=pgr,
        disposition_plr=plr,
        disposition_dei=dei,
        loss_aversion_index=lai,
        computed_at=datetime.utcnow(),
    )
    db_session.add(metric)
    db_session.flush()
    return metric
