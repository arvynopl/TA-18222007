"""
modules/utils/research_export.py — Cohort-level data export helpers for the
researcher view.

Pure functions (no Streamlit imports) that aggregate across all users for the
researcher dashboard. Mirrors the style of ``modules/utils/export.py`` but
operates at the cohort level rather than per-session/per-user.

Functions:
    get_cohort_summary       — Cohort KPIs (counts, means, completion rate).
    export_all_users_csv     — One row per user, joined with profile/survey/CDT.
    export_all_sessions_csv  — One row per BiasMetric, with derived session_num.
    export_cdt_snapshots_csv — Longitudinal CDT trajectory across all users.
    load_model_performance   — Read ``reports/`` ML validation outputs from disk.
"""

from __future__ import annotations

import csv
import json
import logging
import statistics
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from database.models import (
    BiasMetric, CdtSnapshot, CognitiveProfile, ConsentLog,
    OnboardingSurvey, User, UserAction, UserProfile, UserSurvey,
)

logger = logging.getLogger(__name__)


def _round(value: Optional[float], ndigits: int = 4) -> float:
    """Round a possibly-None numeric to ``ndigits``; ``None`` → 0.0."""
    if value is None:
        return 0.0
    return round(float(value), ndigits)


def _mean_sd(values: list[float]) -> tuple[float, float]:
    """Return (mean, sd) for a list, both rounded to 4 decimals.

    Returns (0.0, 0.0) on an empty list. SD uses sample stdev when n ≥ 2,
    else 0.0.
    """
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    sd = statistics.stdev(values) if len(values) >= 2 else 0.0
    return round(mean, 4), round(sd, 4)


def get_cohort_summary(db_session: Session) -> dict:
    """Return cohort-level KPIs.

    Keys: total_users, total_sessions, users_with_consent, users_with_survey,
          users_with_min_3_sessions, mean_dei, sd_dei, mean_ocs, sd_ocs,
          mean_lai, sd_lai, mean_stability_index, completion_rate.

    completion_rate = users_with_min_3_sessions / total_users (0.0 when no users).
    All numeric fields are floats rounded to 4 decimals. Empty cohort returns
    zeros (never None).
    """
    total_users = db_session.query(User).count()
    total_sessions = db_session.query(BiasMetric).count()

    users_with_consent = (
        db_session.query(ConsentLog.user_id)
        .filter(ConsentLog.consent_given.is_(True))
        .distinct()
        .count()
    )
    users_with_survey = db_session.query(OnboardingSurvey).count()

    # Per-user session counts to derive "≥3 sessions" cohort and completion_rate.
    session_counts: dict[int, int] = {}
    for (uid,) in db_session.query(BiasMetric.user_id).all():
        session_counts[uid] = session_counts.get(uid, 0) + 1
    users_with_min_3_sessions = sum(1 for c in session_counts.values() if c >= 3)

    completion_rate = (
        users_with_min_3_sessions / total_users if total_users else 0.0
    )

    metrics = db_session.query(BiasMetric).all()
    dei_values = [
        abs(m.disposition_dei) for m in metrics if m.disposition_dei is not None
    ]
    ocs_values = [
        m.overconfidence_score for m in metrics if m.overconfidence_score is not None
    ]
    lai_values = [
        m.loss_aversion_index for m in metrics if m.loss_aversion_index is not None
    ]
    mean_dei, sd_dei = _mean_sd(dei_values)
    mean_ocs, sd_ocs = _mean_sd(ocs_values)
    mean_lai, sd_lai = _mean_sd(lai_values)

    profiles = db_session.query(CognitiveProfile).all()
    stability_values = [
        p.stability_index for p in profiles if p.stability_index is not None
    ]
    mean_stability = round(
        sum(stability_values) / len(stability_values), 4
    ) if stability_values else 0.0

    return {
        "total_users": int(total_users),
        "total_sessions": int(total_sessions),
        "users_with_consent": int(users_with_consent),
        "users_with_survey": int(users_with_survey),
        "users_with_min_3_sessions": int(users_with_min_3_sessions),
        "mean_dei": mean_dei,
        "sd_dei": sd_dei,
        "mean_ocs": mean_ocs,
        "sd_ocs": sd_ocs,
        "mean_lai": mean_lai,
        "sd_lai": sd_lai,
        "mean_stability_index": mean_stability,
        "completion_rate": round(completion_rate, 4),
    }


def export_all_users_csv(db_session: Session) -> list[dict]:
    """Cohort-level per-user export. One row per User.

    Columns:
        user_id, username, age, gender, risk_profile, investing_capability,
        consent_given, registered_at, session_count,
        onboarding_dei_q1, onboarding_dei_q2, onboarding_dei_q3,
        onboarding_ocs_q1, onboarding_ocs_q2, onboarding_ocs_q3,
        onboarding_lai_q1, onboarding_lai_q2, onboarding_lai_q3,
        survey_risk_tolerance, survey_loss_sensitivity,
        survey_trading_frequency, survey_holding_behavior,
        cdt_overconfidence, cdt_disposition, cdt_loss_aversion,
        risk_preference, stability_index, last_updated_at.
    """
    users = db_session.query(User).order_by(User.id).all()
    profiles = {p.user_id: p for p in db_session.query(UserProfile).all()}
    onboards = {o.user_id: o for o in db_session.query(OnboardingSurvey).all()}
    surveys = {s.user_id: s for s in db_session.query(UserSurvey).all()}
    cdts = {c.user_id: c for c in db_session.query(CognitiveProfile).all()}

    consent_user_ids = {
        uid for (uid,) in (
            db_session.query(ConsentLog.user_id)
            .filter(ConsentLog.consent_given.is_(True))
            .distinct()
            .all()
        )
    }

    session_counts: dict[int, int] = {}
    for (uid,) in db_session.query(BiasMetric.user_id).all():
        session_counts[uid] = session_counts.get(uid, 0) + 1

    rows: list[dict] = []
    for u in users:
        prof = profiles.get(u.id)
        onb = onboards.get(u.id)
        srv = surveys.get(u.id)
        cdt = cdts.get(u.id)
        bv = (cdt.bias_intensity_vector or {}) if cdt else {}

        rows.append({
            "user_id": u.id,
            "username": u.username or u.alias,
            "age": prof.age if prof else None,
            "gender": prof.gender if prof else None,
            "risk_profile": prof.risk_profile if prof else None,
            "investing_capability": prof.investing_capability if prof else None,
            "consent_given": u.id in consent_user_ids,
            "registered_at": u.created_at.isoformat() if u.created_at else None,
            "session_count": session_counts.get(u.id, 0),
            "onboarding_dei_q1": onb.dei_q1 if onb else None,
            "onboarding_dei_q2": onb.dei_q2 if onb else None,
            "onboarding_dei_q3": onb.dei_q3 if onb else None,
            "onboarding_ocs_q1": onb.ocs_q1 if onb else None,
            "onboarding_ocs_q2": onb.ocs_q2 if onb else None,
            "onboarding_ocs_q3": onb.ocs_q3 if onb else None,
            "onboarding_lai_q1": onb.lai_q1 if onb else None,
            "onboarding_lai_q2": onb.lai_q2 if onb else None,
            "onboarding_lai_q3": onb.lai_q3 if onb else None,
            "survey_risk_tolerance": srv.q_risk_tolerance if srv else None,
            "survey_loss_sensitivity": srv.q_loss_sensitivity if srv else None,
            "survey_trading_frequency": srv.q_trading_frequency if srv else None,
            "survey_holding_behavior": srv.q_holding_behavior if srv else None,
            "cdt_overconfidence": bv.get("overconfidence") if cdt else None,
            "cdt_disposition": bv.get("disposition") if cdt else None,
            "cdt_loss_aversion": bv.get("loss_aversion") if cdt else None,
            "risk_preference": cdt.risk_preference if cdt else None,
            "stability_index": cdt.stability_index if cdt else None,
            "last_updated_at": (
                cdt.last_updated_at.isoformat()
                if cdt and cdt.last_updated_at else None
            ),
        })
    return rows


def export_all_sessions_csv(db_session: Session) -> list[dict]:
    """One row per BiasMetric (i.e. per completed session).

    Columns:
        user_id, username, session_id, session_num (1-indexed within user),
        pgr, plr, dei, ocs, lai, computed_at, action_count.
    Ordered by user_id then computed_at.
    """
    metrics = (
        db_session.query(BiasMetric)
        .order_by(BiasMetric.user_id, BiasMetric.computed_at)
        .all()
    )
    users = {u.id: u for u in db_session.query(User).all()}

    # Build action counts grouped by (user_id, session_id) in one query.
    action_counts: dict[tuple[int, str], int] = {}
    for ua_user_id, ua_session_id in (
        db_session.query(UserAction.user_id, UserAction.session_id).all()
    ):
        key = (ua_user_id, ua_session_id)
        action_counts[key] = action_counts.get(key, 0) + 1

    per_user_idx: dict[int, int] = {}
    rows: list[dict] = []
    for m in metrics:
        per_user_idx[m.user_id] = per_user_idx.get(m.user_id, 0) + 1
        u = users.get(m.user_id)
        rows.append({
            "user_id": m.user_id,
            "username": (u.username or u.alias) if u else None,
            "session_id": m.session_id,
            "session_num": per_user_idx[m.user_id],
            "pgr": m.disposition_pgr,
            "plr": m.disposition_plr,
            "dei": m.disposition_dei,
            "ocs": m.overconfidence_score,
            "lai": m.loss_aversion_index,
            "computed_at": m.computed_at.isoformat() if m.computed_at else None,
            "action_count": action_counts.get((m.user_id, m.session_id), 0),
        })
    return rows


def export_cdt_snapshots_csv(db_session: Session) -> list[dict]:
    """Longitudinal CDT trajectory. One row per CdtSnapshot.

    Columns:
        user_id, username, session_number, cdt_overconfidence,
        cdt_disposition, cdt_loss_aversion, captured_at.
    Ordered by user_id then session_number.
    """
    snapshots = (
        db_session.query(CdtSnapshot)
        .order_by(CdtSnapshot.user_id, CdtSnapshot.session_number)
        .all()
    )
    users = {u.id: u for u in db_session.query(User).all()}

    rows: list[dict] = []
    for s in snapshots:
        u = users.get(s.user_id)
        rows.append({
            "user_id": s.user_id,
            "username": (u.username or u.alias) if u else None,
            "session_number": s.session_number,
            "cdt_overconfidence": s.cdt_overconfidence,
            "cdt_disposition": s.cdt_disposition,
            "cdt_loss_aversion": s.cdt_loss_aversion,
            "captured_at": (
                s.snapshotted_at.isoformat() if s.snapshotted_at else None
            ),
        })
    return rows


def load_model_performance(reports_dir: str | Path = "reports") -> dict:
    """Load ML validation outputs from disk.

    Returns a dict with keys:
        available, summary, classification_report,
        feature_importance_path, decision_tree_path, generated_at.

    Missing files → ``available=False``; never raises.
    """
    reports_path = Path(reports_dir)
    out: dict = {
        "available": False,
        "summary": None,
        "classification_report": None,
        "feature_importance_path": None,
        "decision_tree_path": None,
        "generated_at": None,
    }

    if not reports_path.exists():
        logger.info("Model performance reports dir not found: %s", reports_path)
        return out

    summary_file = reports_path / "ml_summary.json"
    classification_file = reports_path / "ml_classification_report.csv"
    feature_png = reports_path / "ml_feature_importance.png"
    tree_png = reports_path / "ml_decision_tree.png"

    if summary_file.exists():
        try:
            with open(summary_file, encoding="utf-8") as fh:
                summary = json.load(fh)
            out["summary"] = summary
            out["generated_at"] = summary.get("generated_at")
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load %s", summary_file)

    if classification_file.exists():
        try:
            with open(classification_file, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                out["classification_report"] = list(reader)
        except OSError:
            logger.exception("Failed to load %s", classification_file)

    if feature_png.exists():
        out["feature_importance_path"] = str(feature_png)
    if tree_png.exists():
        out["decision_tree_path"] = str(tree_png)

    out["available"] = bool(out["summary"] or out["classification_report"])
    return out
