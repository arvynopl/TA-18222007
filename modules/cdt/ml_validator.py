"""
modules/cdt/ml_validator.py — Isolation Forest anomaly detection for CDT validation.

Validates the CDT bias detection system (FR02 support) by applying an unsupervised
Isolation Forest to the user's session-level bias scores. Sessions whose bias vectors
deviate significantly from the user's own behavioral baseline are flagged as anomalous.

This provides a lightweight ML validation layer without supervised labels, consistent
with the small-sample constraints of the thesis UAT (N ≈ 10–15 participants).

Functions:
    compute_anomaly_flags — Returns per-session anomaly scores and flag labels.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from config import LAI_EMA_CEILING
from database.models import BiasMetric

logger = logging.getLogger(__name__)

_MIN_SESSIONS_FOR_ML = 5
_ISOLATION_FOREST_CONTAMINATION = 0.1  # assume ~10% of sessions are structural outliers


def compute_anomaly_flags(
    db_session: Session, user_id: int
) -> Optional[dict]:
    """Apply Isolation Forest to the user's bias history to detect anomalous sessions.

    Features per session (all normalised to [0,1]):
        - OCS (already in [0,1))
        - |DEI| (absolute value)
        - LAI_norm = min(LAI / LAI_EMA_CEILING, 1.0)

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user.

    Returns:
        Dict with keys:
            "session_ids":    List[str] — session UUIDs in chronological order.
            "anomaly_scores": List[float] — Isolation Forest anomaly scores.
                              More negative = more anomalous (sklearn convention).
            "is_anomaly":     List[bool] — True if score < 0 (sklearn flags as outlier).
            "n_sessions":     int — number of sessions used.
        Returns None if sklearn unavailable, or fewer than _MIN_SESSIONS_FOR_ML sessions.
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        logger.warning("scikit-learn not installed — ML anomaly detection unavailable.")
        return None

    metrics = (
        db_session.query(BiasMetric)
        .filter_by(user_id=user_id)
        .order_by(BiasMetric.computed_at)
        .all()
    )

    if len(metrics) < _MIN_SESSIONS_FOR_ML:
        return None

    X = [
        [
            m.overconfidence_score or 0.0,
            abs(m.disposition_dei or 0.0),
            min((m.loss_aversion_index or 0.0) / LAI_EMA_CEILING, 1.0),
        ]
        for m in metrics
    ]

    try:
        clf = IsolationForest(
            contamination=_ISOLATION_FOREST_CONTAMINATION,
            random_state=42,
            n_estimators=100,
        )
        clf.fit(X)
        raw_scores = clf.score_samples(X).tolist()   # more negative = more anomalous
        predictions = clf.predict(X).tolist()         # -1 = anomaly, 1 = normal
        is_anomaly = [p == -1 for p in predictions]
    except Exception as exc:
        logger.warning("IsolationForest failed: %s", exc)
        return None

    result = {
        "session_ids": [m.session_id for m in metrics],
        "anomaly_scores": raw_scores,
        "is_anomaly": is_anomaly,
        "n_sessions": len(metrics),
    }
    anomaly_count = sum(is_anomaly)
    logger.debug(
        "user=%s IsolationForest: %d sessions, %d anomalous",
        user_id, len(metrics), anomaly_count,
    )
    return result
