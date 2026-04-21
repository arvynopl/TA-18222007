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
    compute_disposition_effect      → (pgr, plr, dei)
    compute_overconfidence_score    → float
    compute_loss_aversion_index     → float
    classify_severity               → str
    compute_bias_metrics_with_ci    → BiasMetricsWithCI
    compute_and_save_metrics        → BiasMetric
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean, stdev

from sqlalchemy.orm import Session

import logging

from config import (
    DEI_MILD, DEI_MODERATE, DEI_SEVERE,
    LAI_MILD, LAI_MODERATE, LAI_SEVERE,
    OCS_MILD, OCS_MODERATE, OCS_SEVERE,
    ROUNDS_PER_SESSION,
)

logger = logging.getLogger(__name__)
from database.models import BiasMetric
from modules.analytics.features import SessionFeatures, extract_session_features


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BiasMetricsWithCI:
    """Point estimates and bootstrapped 95% confidence intervals for all bias metrics.

    Attributes:
        dei:          Disposition Effect Index point estimate.
        dei_ci:       (lower_95, upper_95) bootstrap CI for DEI.
        ocs:          Overconfidence Score point estimate.
        ocs_ci:       (lower_95, upper_95) bootstrap CI for OCS.
        lai:          Loss Aversion Index point estimate.
        lai_ci:       (lower_95, upper_95) bootstrap CI for LAI.
        dei_severity: Severity label for DEI ("none"/"mild"/"moderate"/"severe").
        ocs_severity: Severity label for OCS.
        lai_severity: Severity label for LAI.
        low_confidence: True when the session has fewer than 5 realized trades;
                        all CIs degenerate to (metric, metric) in that case.
    """

    dei: float
    dei_ci: tuple[float, float]
    ocs: float
    ocs_ci: tuple[float, float]
    lai: float
    lai_ci: tuple[float, float]
    dei_severity: str
    ocs_severity: str
    lai_severity: str
    low_confidence: bool = False


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

    OCS = 2 × (sigmoid(raw) − 0.5), mapping [0,∞) → [0,1)
    This preserves sigmoid smoothing while ensuring zero-activity → OCS = 0.

    trade_frequency   = (buy_count + sell_count) / ROUNDS_PER_SESSION
    performance_ratio = final_value / initial_value
    raw               = trade_frequency / max(performance_ratio, 0.01)

    Threshold calibration (14-round session, Barber & Odean 2000):
        - All-hold (0 trades):              raw = 0.000 → OCS = 0.000 → "none" ✓
        - Buy-and-hold (1 trade, perf=1.0): raw = 0.071 → OCS = 0.036 → "none" ✓
        - Moderate trader (8 trades, perf=0.95):
                                            raw = 0.602 → OCS = 0.292 → "mild" ✓
        - Active trader (14 trades, perf=0.85):
                                            raw = 1.176 → OCS = 0.529 → "moderate" ✓
        - Heavy overtrader (20+ trades equiv, perf=0.70):
                                            raw = 2.041 → OCS = 0.770 → "severe" ✓

    Args:
        features: Extracted session features.

    Returns:
        Float in [0, 1).
    """
    trade_frequency = (features.buy_count + features.sell_count) / ROUNDS_PER_SESSION
    performance_ratio = features.final_value / max(features.initial_value, 1.0)
    raw = trade_frequency / max(performance_ratio, 0.01)
    return 2.0 * (_sigmoid(raw) - 0.5)


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

    Edge-case semantics (by design — consistent with Odean 1998 counting approach):
        - No realized trades at all → LAI = 0.0  ("insufficient data"; not "no aversion")
        - Only winning trades sold  → avg_losers = 0.0  → LAI = 0.0
          Interpretation: user never held losers, so no loss-aversion signal.
        - Only losing trades sold   → avg_winners = 0.0 → denominator clamped to 1.0
          → LAI = avg_losers (raw rounds). Can be > 1 without a winner baseline.

    Callers should be aware that LAI = 0.0 may mean "no data" rather than
    "zero loss aversion". Check features.realized_trades before interpreting.

    Args:
        features: Extracted session features.

    Returns:
        Float ≥ 0.
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

    if not loser_holds and not winner_holds:
        logger.debug(
            "LAI: user=%s session=%s no realized trades — returning 0.0 (insufficient data)",
            features.user_id, features.session_id,
        )
    elif not loser_holds:
        logger.debug(
            "LAI: user=%s session=%s only winning trades — returning 0.0 (no loser signal)",
            features.user_id, features.session_id,
        )
    elif not winner_holds:
        logger.debug(
            "LAI: user=%s session=%s only losing trades — avg_winners clamped to 1.0",
            features.user_id, features.session_id,
        )

    return avg_losers / max(avg_winners, 1.0)


# ---------------------------------------------------------------------------
# Severity classifier
# ---------------------------------------------------------------------------

def classify_severity(
    value: float,
    severe_threshold: float,
    moderate_threshold: float,
    mild_t: float | None = None,
    min_sample_met: bool = True,
) -> str:
    """Map a metric value to a severity label.

    Args:
        value:              The computed metric value.
        severe_threshold:   Value at or above which severity = "severe".
        moderate_threshold: Value at or above which severity = "moderate".
        mild_t:             Optional value at or above which severity = "mild".
        min_sample_met:     If False, severity is capped at "mild" regardless of value.
                            Use when the realized trade count is below the
                            MIN_TRADES_FOR_FULL_SEVERITY threshold (insufficient sample
                            for DEI and LAI to be meaningfully classified as
                            moderate/severe). Default True preserves existing behaviour.

    Returns:
        "severe", "moderate", "mild", or "none".
    """
    if not min_sample_met:
        # Insufficient realized trades → cap at "mild"
        if mild_t is not None and value >= mild_t:
            return "mild"
        return "none"
    if value >= severe_threshold:
        return "severe"
    if value >= moderate_threshold:
        return "moderate"
    if mild_t is not None and value >= mild_t:
        return "mild"
    return "none"


# ---------------------------------------------------------------------------
# Bootstrapped confidence intervals
# ---------------------------------------------------------------------------

_MIN_TRADES_FOR_CI = 5  # minimum realized trades required for non-degenerate CIs


def _percentile_ci(samples: list[float]) -> tuple[float, float]:
    """Return the (2.5th, 97.5th) percentile of *samples* with linear interpolation.

    Matches NumPy's default interpolation method so results are directly
    comparable to scientific references.

    Args:
        samples: Bootstrap replicate values (need not be sorted).

    Returns:
        (lower_95, upper_95) tuple.
    """
    if not samples:
        return 0.0, 0.0
    n = len(samples)
    sorted_s = sorted(samples)

    def _p(pct: float) -> float:
        idx = (pct / 100.0) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_s[lo] + frac * (sorted_s[hi] - sorted_s[lo])

    return _p(2.5), _p(97.5)


def _bootstrap_features(
    features: SessionFeatures,
    rng: random.Random,
) -> SessionFeatures:
    """Return one bootstrap replicate of *features* by resampling trade-level data.

    Resamples ``realized_trades`` and ``open_positions`` independently with
    replacement, keeping the same sample sizes.  OCS-relevant aggregate counts
    (``buy_count``, ``sell_count``) and ``final_value`` are re-derived from the
    resampled trade data so every metric receives internally consistent inputs.

    Note: ``buy_count`` and ``sell_count`` are approximated as one action per
    completed round-trip and one buy per open position — a deliberate
    simplification that preserves the bootstrap's uncertainty signal for OCS
    while avoiding unbounded inflation from raw action counts.

    Args:
        features: Original session features.
        rng:      Caller-owned Random instance (keeps global state untouched).

    Returns:
        A new SessionFeatures populated with the resampled data.
    """
    n_realized = len(features.realized_trades)
    n_open = len(features.open_positions)

    rt_b = rng.choices(features.realized_trades, k=n_realized) if n_realized > 0 else []
    op_b = rng.choices(features.open_positions, k=n_open) if n_open > 0 else []

    f_b = SessionFeatures(user_id=features.user_id, session_id=features.session_id)
    f_b.realized_trades = rt_b
    f_b.open_positions = op_b
    f_b.initial_value = features.initial_value

    # Each completed round-trip counts as one buy + one sell action;
    # each open position counts as one buy action (no matching sell yet).
    f_b.buy_count = n_realized + n_open
    f_b.sell_count = n_realized

    # Approximate final portfolio value from resampled P&L contributions.
    realized_pnl = sum(
        (t["sell_price"] - t["buy_price"]) * t["quantity"] for t in rt_b
    )
    unrealized_pnl = sum(p.get("unrealized_pnl", 0.0) for p in op_b)
    f_b.final_value = max(features.initial_value + realized_pnl + unrealized_pnl, 1.0)

    return f_b


def compute_bias_metrics_with_ci(
    session_features: SessionFeatures,
    n_bootstrap: int = 500,
) -> BiasMetricsWithCI:
    """Compute all three bias metrics with bootstrapped 95% confidence intervals.

    Resamples the underlying trade-level data (``realized_trades``,
    ``open_positions``) *n_bootstrap* times with replacement, recomputes each
    metric per replicate, and reports the 2.5th and 97.5th percentiles as the
    95% CI.

    When the session has fewer than ``_MIN_TRADES_FOR_CI`` (5) realized trades,
    the bootstrap is skipped: all three CIs degenerate to ``(metric, metric)``
    and ``low_confidence`` is set to ``True``.

    The internal RNG is seeded deterministically so repeated calls with the
    same inputs always return the same CIs.

    Args:
        session_features: Extracted session features.
        n_bootstrap:      Number of bootstrap replicates (default 500).

    Returns:
        :class:`BiasMetricsWithCI` with point estimates, 95% CIs, severity
        labels, and a ``low_confidence`` flag.
    """
    _, _, dei = compute_disposition_effect(session_features)
    ocs = compute_overconfidence_score(session_features)
    lai = compute_loss_aversion_index(session_features)

    dei_severity = classify_severity(abs(dei), DEI_SEVERE, DEI_MODERATE, DEI_MILD)
    ocs_severity = classify_severity(ocs, OCS_SEVERE, OCS_MODERATE, OCS_MILD)
    lai_severity = classify_severity(lai, LAI_SEVERE, LAI_MODERATE, LAI_MILD)

    n_realized = len(session_features.realized_trades)
    if n_realized < _MIN_TRADES_FOR_CI:
        logger.debug(
            "compute_bias_metrics_with_ci: user=%s session=%s — only %d realized trades, "
            "CI degenerated to point estimate (low_confidence=True)",
            session_features.user_id, session_features.session_id, n_realized,
        )
        return BiasMetricsWithCI(
            dei=dei, dei_ci=(dei, dei),
            ocs=ocs, ocs_ci=(ocs, ocs),
            lai=lai, lai_ci=(lai, lai),
            dei_severity=dei_severity,
            ocs_severity=ocs_severity,
            lai_severity=lai_severity,
            low_confidence=True,
        )

    rng = random.Random(0)
    dei_samples: list[float] = []
    ocs_samples: list[float] = []
    lai_samples: list[float] = []

    for _ in range(n_bootstrap):
        f_b = _bootstrap_features(session_features, rng)
        _, _, dei_b = compute_disposition_effect(f_b)
        ocs_b = compute_overconfidence_score(f_b)
        lai_b = compute_loss_aversion_index(f_b)
        dei_samples.append(dei_b)
        ocs_samples.append(ocs_b)
        lai_samples.append(lai_b)

    dei_ci = _percentile_ci(dei_samples)
    ocs_ci = _percentile_ci(ocs_samples)
    lai_ci = _percentile_ci(lai_samples)

    logger.debug(
        "compute_bias_metrics_with_ci: user=%s session=%s n_bootstrap=%d "
        "DEI=%.3f CI=[%.3f, %.3f] OCS=%.3f CI=[%.3f, %.3f] LAI=%.3f CI=[%.3f, %.3f]",
        session_features.user_id, session_features.session_id, n_bootstrap,
        dei, dei_ci[0], dei_ci[1],
        ocs, ocs_ci[0], ocs_ci[1],
        lai, lai_ci[0], lai_ci[1],
    )

    return BiasMetricsWithCI(
        dei=dei, dei_ci=dei_ci,
        ocs=ocs, ocs_ci=ocs_ci,
        lai=lai, lai_ci=lai_ci,
        dei_severity=dei_severity,
        ocs_severity=ocs_severity,
        lai_severity=lai_severity,
        low_confidence=False,
    )


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

    result = compute_bias_metrics_with_ci(features)
    pgr, plr, _ = compute_disposition_effect(features)

    logger.debug(
        "user=%s session=%s OCS=%.3f(%s) DEI=%.3f(%s) LAI=%.3f(%s)",
        user_id, session_id[:8],
        result.ocs, result.ocs_severity,
        result.dei, result.dei_severity,
        result.lai, result.lai_severity,
    )

    metric = BiasMetric(
        user_id=user_id,
        session_id=session_id,
        overconfidence_score=result.ocs,
        disposition_pgr=pgr,
        disposition_plr=plr,
        disposition_dei=result.dei,
        loss_aversion_index=result.lai,
        dei_ci_lower=result.dei_ci[0],
        dei_ci_upper=result.dei_ci[1],
        ocs_ci_lower=result.ocs_ci[0],
        ocs_ci_upper=result.ocs_ci[1],
        lai_ci_lower=result.lai_ci[0],
        lai_ci_upper=result.lai_ci[1],
        ci_low_confidence=result.low_confidence,
        computed_at=datetime.now(timezone.utc),
    )
    db_session.add(metric)
    db_session.flush()
    return metric
