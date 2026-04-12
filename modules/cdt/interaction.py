"""
modules/cdt/interaction.py — Cross-bias interaction score computation.

Computes pairwise Pearson correlation coefficients between OCS, |DEI|, and
normalised LAI across recent sessions, capturing coupled behavioral patterns.

Functions:
    compute_interaction_scores — Returns a dict of pairwise correlations.
"""

from __future__ import annotations

import math
from typing import Optional

from sqlalchemy.orm import Session

from config import CDT_STABILITY_WINDOW, LAI_EMA_CEILING
from database.models import BiasMetric

import logging

logger = logging.getLogger(__name__)

_MIN_SESSIONS_FOR_INTERACTION = 3


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    """Compute Pearson r between two equal-length series.

    Returns None if n < 2, or if either series has zero variance.
    """
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None

    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / (n - 1))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / (n - 1))

    if sx < 1e-9 or sy < 1e-9:
        return None  # zero-variance series → undefined correlation

    return max(-1.0, min(1.0, cov / (sx * sy)))  # clamp to [-1,1] for float safety


def compute_interaction_scores(
    db_session: Session, user_id: int
) -> Optional[dict]:
    """Compute pairwise Pearson correlations between bias metrics across sessions.

    Uses the last CDT_STABILITY_WINDOW sessions (same window as stability index).
    Returns None when fewer than _MIN_SESSIONS_FOR_INTERACTION sessions exist.

    Normalisation applied before correlation (same as stability index):
        - OCS: already in [0,1) — unchanged.
        - DEI: |DEI| (absolute value, capturing magnitude regardless of sign).
        - LAI: min(LAI / LAI_EMA_CEILING, 1.0).

    Returns:
        Dict with keys "ocs_dei", "ocs_lai", "dei_lai" — each a float in [-1,1]
        or None if either series has zero variance. Returns None if insufficient
        sessions.
    """
    metrics = (
        db_session.query(BiasMetric)
        .filter_by(user_id=user_id)
        .order_by(BiasMetric.computed_at.desc())
        .limit(CDT_STABILITY_WINDOW)
        .all()
    )

    if len(metrics) < _MIN_SESSIONS_FOR_INTERACTION:
        return None

    ocs_vals = [m.overconfidence_score or 0.0 for m in metrics]
    dei_vals = [abs(m.disposition_dei or 0.0) for m in metrics]
    lai_vals = [min((m.loss_aversion_index or 0.0) / LAI_EMA_CEILING, 1.0) for m in metrics]

    result = {
        "ocs_dei": _pearson(ocs_vals, dei_vals),
        "ocs_lai": _pearson(ocs_vals, lai_vals),
        "dei_lai": _pearson(dei_vals, lai_vals),
    }

    logger.debug(
        "user=%s interaction_scores: ocs_dei=%.3f ocs_lai=%.3f dei_lai=%.3f",
        user_id,
        result["ocs_dei"] if result["ocs_dei"] is not None else float("nan"),
        result["ocs_lai"] if result["ocs_lai"] is not None else float("nan"),
        result["dei_lai"] if result["dei_lai"] is not None else float("nan"),
    )
    return result
