"""
modules/cdt/stability.py — Stability index computation.

The stability index measures how consistent a user's bias pattern is across
recent sessions: high stability = consistent behaviour (not necessarily good).

Functions:
    compute_stability_index — Returns a float in [0, 1].
"""

from __future__ import annotations

import math

from sqlalchemy.orm import Session

from config import CDT_STABILITY_WINDOW
from database.models import BiasMetric


def compute_stability_index(db_session: Session, user_id: int) -> float:
    """Compute the stability index from the last CDT_STABILITY_WINDOW sessions.

    Algorithm:
        1. Fetch the last N BiasMetric rows for the user (ordered by computed_at).
        2. For each bias dimension (overconfidence, DEI, LAI), normalise the
           metric to [0, 1] and compute the standard deviation across sessions.
        3. stability = 1 − mean(std_overconfidence, std_dei_norm, std_lai_norm)
           clamped to [0, 1].

    Fewer than 2 sessions → returns 0.0 (insufficient data).

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user.

    Returns:
        Float in [0, 1] — higher = more consistent bias pattern.
    """
    metrics = (
        db_session.query(BiasMetric)
        .filter_by(user_id=user_id)
        .order_by(BiasMetric.computed_at.desc())
        .limit(CDT_STABILITY_WINDOW)
        .all()
    )

    if len(metrics) < 2:
        return 0.0

    ocs_vals = [m.overconfidence_score or 0.0 for m in metrics]
    # Use raw (signed) DEI so oscillation between positive and negative values
    # registers as high variance (erratic behaviour).
    dei_vals = [(m.disposition_dei or 0.0) for m in metrics]
    lai_vals = [min((m.loss_aversion_index or 0.0) / 3.0, 1.0) for m in metrics]

    def _std(vals: list[float]) -> float:
        n = len(vals)
        if n < 2:
            return 0.0
        mu = sum(vals) / n
        variance = sum((v - mu) ** 2 for v in vals) / (n - 1)
        return math.sqrt(variance)

    mean_std = (_std(ocs_vals) + _std(dei_vals) + _std(lai_vals)) / 3.0
    return max(0.0, min(1.0, 1.0 - mean_std))
