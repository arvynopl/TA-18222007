"""
modules/cdt/ml_validator.py — ML validation layer for the CDT Bias Detection System.

Two complementary validation strategies are provided:

1. **Isolation Forest** (unsupervised) — ``compute_anomaly_flags``
   Flags sessions whose bias vectors deviate from the user's own behavioural
   baseline. Requires no labels; suitable for live, per-user anomaly detection.

2. **Decision Tree Classifier** (supervised) — ``train_bias_classifier``
   Validates that the deterministic bias formulas (OCS/DEI/LAI) produce
   severity labels that are learnable from raw behavioural features.  Used
   offline by ``scripts/run_ml_validation.py`` to generate publication-quality
   feature importance charts and classification reports for Bab VI of the thesis.

Public functions:
    compute_anomaly_flags   — Per-session anomaly scores (IsolationForest).
    derive_worst_severity   — Map (OCS, DEI, LAI) → worst severity label.
    build_feature_matrix    — Build (X, y) from BiasMetric + SessionFeatures.
    train_bias_classifier   — Fit DecisionTree; return metrics dict.

Exported constants:
    SEVERITY_ORDER            — {"none":0, "mild":1, "moderate":2, "severe":3}
    DECISION_TREE_FEATURE_NAMES — ordered list of 10 feature keys.
    FEATURE_LABELS_ID          — Bahasa Indonesia display labels for charts.
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


# ---------------------------------------------------------------------------
# Decision-tree classifier for bias classification validation (Bab VI)
# ---------------------------------------------------------------------------

#: Numeric ordering of severity labels — used for argmax comparisons.
SEVERITY_ORDER: dict[str, int] = {"none": 0, "mild": 1, "moderate": 2, "severe": 3}

#: Ordered feature names used for the decision-tree feature matrix (10 dims).
DECISION_TREE_FEATURE_NAMES: list[str] = [
    "ocs",
    "abs_dei",
    "lai_norm",
    "pgr",
    "plr",
    "trade_frequency",
    "hold_ratio",
    "portfolio_return_pct",
    "realized_count_norm",
    "ocs_x_lai",
]

#: Bahasa Indonesia display labels keyed by feature name (for thesis charts).
FEATURE_LABELS_ID: dict[str, str] = {
    "ocs":                  "Skor Overconfidence (OCS)",
    "abs_dei":              "|Indeks Efek Disposisi (DEI)|",
    "lai_norm":             "Indeks Aversi Kerugian (LAI, norm.)",
    "pgr":                  "Rasio Realisasi Keuntungan (PGR)",
    "plr":                  "Rasio Realisasi Kerugian (PLR)",
    "trade_frequency":      "Frekuensi Perdagangan",
    "hold_ratio":           "Rasio Tahan (Hold)",
    "portfolio_return_pct": "Return Portofolio (fraksi)",
    "realized_count_norm":  "Jml. Perdagangan Terealisasi (norm.)",
    "ocs_x_lai":            "Interaksi OCS \u00d7 LAI",
}


def derive_worst_severity(ocs: float, dei: float, lai: float) -> str:
    """Return the worst-case severity label across all three bias dimensions.

    Uses the canonical thresholds from ``config.py`` so that the decision-tree
    training labels stay consistent with the rest of the CDT pipeline.

    Args:
        ocs:  Overconfidence Score (already in [0, 1)).
        dei:  Disposition Effect Index (signed; |dei| compared against thresholds).
        lai:  Loss Aversion Index (raw, unnormalised).

    Returns:
        One of ``"severe"`` | ``"moderate"`` | ``"mild"`` | ``"none"``.
    """
    from config import (
        DEI_MILD, DEI_MODERATE, DEI_SEVERE,
        LAI_MILD, LAI_MODERATE, LAI_SEVERE,
        OCS_MILD, OCS_MODERATE, OCS_SEVERE,
    )

    def _clf(val: float, mild: float, mod: float, severe: float) -> str:
        if val >= severe:
            return "severe"
        if val >= mod:
            return "moderate"
        if val >= mild:
            return "mild"
        return "none"

    scores = [
        _clf(ocs, OCS_MILD, OCS_MODERATE, OCS_SEVERE),
        _clf(abs(dei), DEI_MILD, DEI_MODERATE, DEI_SEVERE),
        _clf(lai, LAI_MILD, LAI_MODERATE, LAI_SEVERE),
    ]
    return max(scores, key=lambda s: SEVERITY_ORDER[s])


def build_feature_matrix(
    db_session: Session,
    metrics: list,
) -> tuple:
    """Build a feature matrix (X, y) from a list of BiasMetric ORM objects.

    Reuses :func:`modules.analytics.features.extract_session_features` to enrich
    each record with session-level behavioural features (trade frequency, hold
    ratio, portfolio return, realised-trade count).  Falls back to metric-derived
    proxies when the corresponding UserAction rows are absent.

    Feature vector layout (10 dims — matches DECISION_TREE_FEATURE_NAMES):
        0  ocs                  OCS score from BiasMetric
        1  abs_dei              |DEI| from BiasMetric
        2  lai_norm             min(LAI / LAI_EMA_CEILING, 1.0)
        3  pgr                  Proportion Gain Realised (BiasMetric)
        4  plr                  Proportion Loss Realised (BiasMetric)
        5  trade_frequency      (buy + sell) / ROUNDS_PER_SESSION  (SessionFeatures)
        6  hold_ratio           hold_count / total_actions          (SessionFeatures)
        7  portfolio_return_pct (final − initial) / initial         (SessionFeatures)
        8  realized_count_norm  min(realized_trade_count / 10, 1.0) (SessionFeatures)
        9  ocs_x_lai            OCS × lai_norm  (interaction term)

    Args:
        db_session: Active SQLAlchemy session.
        metrics:    List of BiasMetric ORM instances.

    Returns:
        Tuple ``(X, y, feature_names)``:
            X            — list[list[float]], shape (n, 10).
            y            — list[str], worst-case severity labels.
            feature_names — :data:`DECISION_TREE_FEATURE_NAMES`.
    """
    from config import LAI_EMA_CEILING, ROUNDS_PER_SESSION
    from modules.analytics.features import extract_session_features

    X: list[list[float]] = []
    y: list[str] = []

    for m in metrics:
        ocs = m.overconfidence_score or 0.0
        dei = m.disposition_dei or 0.0
        pgr = m.disposition_pgr or 0.0
        plr = m.disposition_plr or 0.0
        lai_raw = m.loss_aversion_index or 0.0
        lai_norm = min(lai_raw / LAI_EMA_CEILING, 1.0)

        # Attempt to load session-level features via extract_session_features()
        try:
            sf = extract_session_features(db_session, m.user_id, m.session_id)
            total_actions = sf.buy_count + sf.sell_count + sf.hold_count
            trade_freq = (sf.buy_count + sf.sell_count) / max(ROUNDS_PER_SESSION, 1)
            hold_ratio = sf.hold_count / max(total_actions, 1)
            ret_frac = sf.portfolio_return_pct / 100.0
            realized_norm = min(sf.realized_trade_count / 10.0, 1.0)
        except Exception:
            # No action data available; derive behavioural proxies from metric values
            trade_freq = min(ocs * 0.7, 1.0)
            hold_ratio = max(0.0, 1.0 - trade_freq)
            ret_frac = 0.0
            realized_norm = 0.0

        row = [
            ocs,
            abs(dei),
            lai_norm,
            pgr,
            plr,
            trade_freq,
            hold_ratio,
            ret_frac,
            realized_norm,
            ocs * lai_norm,
        ]
        X.append(row)
        y.append(derive_worst_severity(ocs, dei, lai_raw))

    return X, y, DECISION_TREE_FEATURE_NAMES


def train_bias_classifier(X: list, y: list) -> Optional[dict]:
    """Train a shallow DecisionTreeClassifier on the bias feature matrix.

    The classifier validates that the engineered features (OCS, DEI, LAI plus
    session-level behavioural signals) carry enough discriminatory signal to
    reproduce the deterministic severity labels assigned by the CDT pipeline.

    A shallow tree (``max_depth=4``) is intentional: it stays interpretable,
    can be rendered with ``plot_tree``, and avoids overfitting on the small
    UAT sample sizes typical of thesis work (N ≈ 10–40 sessions).

    Args:
        X: Feature matrix — list of 10-element float lists (n_samples × 10).
        y: Worst-case severity labels — list[str].

    Returns:
        Dict with keys:
            ``"classifier"``    — Fitted :class:`DecisionTreeClassifier`.
            ``"feature_names"`` — Ordered list of feature names.
            ``"y_pred"``        — Predictions on training data (list[str]).
            ``"accuracy"``      — Training accuracy (float).
            ``"report"``        — ``classification_report`` as dict.
            ``"class_counts"``  — Per-class sample counts (dict[str, int]).
            ``"n_samples"``     — Total training sample count (int).
        Returns ``None`` if scikit-learn is unavailable or sample count < 4.
    """
    try:
        import numpy as np
        from sklearn.metrics import classification_report
        from sklearn.tree import DecisionTreeClassifier
    except ImportError:
        logger.warning("scikit-learn not installed — DecisionTreeClassifier unavailable.")
        return None

    if len(X) < 4:
        logger.warning("train_bias_classifier: %d samples < 4, skipping.", len(X))
        return None

    X_arr = np.array(X, dtype=float)

    clf = DecisionTreeClassifier(
        max_depth=4,
        criterion="gini",
        class_weight="balanced",
        min_samples_leaf=2,
        random_state=42,
    )
    clf.fit(X_arr, y)
    y_pred: list[str] = clf.predict(X_arr).tolist()

    accuracy = sum(a == b for a, b in zip(y, y_pred)) / len(y)
    labels_present = sorted(set(y), key=lambda s: SEVERITY_ORDER.get(s, 99))
    report_dict = classification_report(
        y, y_pred, labels=labels_present, output_dict=True, zero_division=0
    )
    class_counts: dict[str, int] = {lbl: y.count(lbl) for lbl in set(y)}

    logger.info(
        "train_bias_classifier: n=%d accuracy=%.3f classes=%s",
        len(y), accuracy, labels_present,
    )
    return {
        "classifier": clf,
        "feature_names": DECISION_TREE_FEATURE_NAMES,
        "y_pred": y_pred,
        "accuracy": accuracy,
        "report": report_dict,
        "class_counts": class_counts,
        "n_samples": len(y),
    }
