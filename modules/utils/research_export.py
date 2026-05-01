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


def _participant_user_ids(db_session: Session) -> set[int]:
    """Return ids of users who count as UAT participants.

    A user is a participant when ANY of the following holds:
      - has an explicit affirmative ConsentLog row (consent_given=True), OR
      - has a UserProfile row (i.e. went through the v6 registration form), OR
      - has a password_hash (proper auth registration).

    This deliberately excludes residual rows that lack all three, e.g. the
    legacy/admin/test seeds (`pgjson_*` aliases from the postgres_compat
    fixtures, or any researcher_admin shell user) which would otherwise
    pollute cohort statistics. Users with at least one BiasMetric *and* a
    ConsentLog also qualify; they're already covered by the consent path.
    """
    consent_ids = {
        uid for (uid,) in (
            db_session.query(ConsentLog.user_id)
            .filter(ConsentLog.consent_given.is_(True))
            .distinct()
            .all()
        )
    }
    profile_ids = {
        uid for (uid,) in (
            db_session.query(UserProfile.user_id).distinct().all()
        )
    }
    auth_ids = {
        uid for (uid,) in (
            db_session.query(User.id)
            .filter(User.password_hash.isnot(None))
            .all()
        )
    }
    return consent_ids | profile_ids | auth_ids


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


def get_cohort_summary(
    db_session: Session,
    *,
    participants_only: bool = False,
) -> dict:
    """Return cohort-level KPIs.

    Keys: total_users, total_sessions, users_with_consent, users_with_survey,
          users_with_min_3_sessions, mean_dei, sd_dei, mean_ocs, sd_ocs,
          mean_lai, sd_lai, mean_stability_index, completion_rate,
          excluded_non_participants.

    completion_rate = users_with_min_3_sessions / total_users (0.0 when no users).
    All numeric fields are floats rounded to 4 decimals. Empty cohort returns
    zeros (never None).

    Args:
      participants_only: When True, exclude users without consent / profile /
        auth credentials. Use this for the researcher dashboard so admin or
        legacy test artifacts don't pollute cohort means. Defaults to False
        for backward compatibility with existing exports/tests.
    """
    qualified: Optional[set[int]] = (
        _participant_user_ids(db_session) if participants_only else None
    )

    base_users_q = db_session.query(User)
    if qualified is not None:
        base_users_q = base_users_q.filter(User.id.in_(qualified))
    total_users = base_users_q.count()
    excluded_non_participants = (
        db_session.query(User).count() - total_users if qualified is not None else 0
    )

    metrics_q = db_session.query(BiasMetric)
    if qualified is not None:
        metrics_q = metrics_q.filter(BiasMetric.user_id.in_(qualified))
    metrics = metrics_q.all()
    total_sessions = len(metrics)

    consent_q = (
        db_session.query(ConsentLog.user_id)
        .filter(ConsentLog.consent_given.is_(True))
        .distinct()
    )
    if qualified is not None:
        consent_q = consent_q.filter(ConsentLog.user_id.in_(qualified))
    users_with_consent = consent_q.count()

    onboard_q = db_session.query(OnboardingSurvey)
    if qualified is not None:
        onboard_q = onboard_q.filter(OnboardingSurvey.user_id.in_(qualified))
    users_with_survey = onboard_q.count()

    # Per-user session counts to derive "≥3 sessions" cohort and completion_rate.
    session_counts: dict[int, int] = {}
    for m in metrics:
        session_counts[m.user_id] = session_counts.get(m.user_id, 0) + 1
    users_with_min_3_sessions = sum(1 for c in session_counts.values() if c >= 3)

    completion_rate = (
        users_with_min_3_sessions / total_users if total_users else 0.0
    )

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

    profiles_q = db_session.query(CognitiveProfile)
    if qualified is not None:
        profiles_q = profiles_q.filter(CognitiveProfile.user_id.in_(qualified))
    profiles = profiles_q.all()
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
        "excluded_non_participants": int(excluded_non_participants),
    }


def export_all_users_csv(
    db_session: Session,
    *,
    participants_only: bool = False,
) -> list[dict]:
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

    Args:
      participants_only: When True, exclude users without consent / profile /
        auth credentials. Use this for the researcher dashboard.
    """
    qualified: Optional[set[int]] = (
        _participant_user_ids(db_session) if participants_only else None
    )
    users_q = db_session.query(User).order_by(User.id)
    if qualified is not None:
        users_q = users_q.filter(User.id.in_(qualified))
    users = users_q.all()
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


def export_all_sessions_csv(
    db_session: Session,
    *,
    participants_only: bool = False,
) -> list[dict]:
    """One row per BiasMetric (i.e. per completed session).

    Columns:
        user_id, username, session_id, session_num (1-indexed within user),
        pgr, plr, dei, ocs, lai, computed_at, action_count.
    Ordered by user_id then computed_at.

    Args:
      participants_only: When True, restrict to qualified UAT participants.
    """
    qualified: Optional[set[int]] = (
        _participant_user_ids(db_session) if participants_only else None
    )
    metrics_q = (
        db_session.query(BiasMetric)
        .order_by(BiasMetric.user_id, BiasMetric.computed_at)
    )
    if qualified is not None:
        metrics_q = metrics_q.filter(BiasMetric.user_id.in_(qualified))
    metrics = metrics_q.all()
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


def export_cdt_snapshots_csv(
    db_session: Session,
    *,
    participants_only: bool = False,
) -> list[dict]:
    """Longitudinal CDT trajectory. One row per CdtSnapshot.

    Columns:
        user_id, username, session_number, cdt_overconfidence,
        cdt_disposition, cdt_loss_aversion, captured_at.
    Ordered by user_id then session_number.

    Args:
      participants_only: When True, restrict to qualified UAT participants.
    """
    qualified: Optional[set[int]] = (
        _participant_user_ids(db_session) if participants_only else None
    )
    snapshots_q = (
        db_session.query(CdtSnapshot)
        .order_by(CdtSnapshot.user_id, CdtSnapshot.session_number)
    )
    if qualified is not None:
        snapshots_q = snapshots_q.filter(CdtSnapshot.user_id.in_(qualified))
    snapshots = snapshots_q.all()
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


def compute_cohort_session_progression(
    db_session: Session,
    *,
    participants_only: bool = True,
) -> list[dict]:
    """Cohort-level bias means aligned by within-user session number.

    Each user's sessions are numbered 1, 2, 3, … in chronological order
    (earliest computed_at = session 1).  Values are then averaged across all
    users who reached that session number, giving a cohort-level progression.

    Returns a list sorted by (session_number, bias).  Each dict has:
        session_number : int   — 1-indexed within each user's history
        bias           : str   — "dei", "ocs", or "lai"
        mean           : float
        sd             : float
        n              : int   — number of users contributing to this point
        values         : list[float] — raw values; useful for bootstrap CI

    Args:
        participants_only: Restrict to qualified UAT participants (default True).
    """
    qualified: Optional[set[int]] = (
        _participant_user_ids(db_session) if participants_only else None
    )
    metrics_q = (
        db_session.query(BiasMetric)
        .order_by(BiasMetric.user_id, BiasMetric.computed_at)
    )
    if qualified is not None:
        metrics_q = metrics_q.filter(BiasMetric.user_id.in_(qualified))
    metrics = metrics_q.all()

    # Group metrics per user (already ordered by computed_at within each user
    # because the query sorts by user_id then computed_at).
    per_user: dict[int, list[BiasMetric]] = {}
    for m in metrics:
        per_user.setdefault(m.user_id, []).append(m)

    dei_by_sess: dict[int, list[float]] = {}
    ocs_by_sess: dict[int, list[float]] = {}
    lai_by_sess: dict[int, list[float]] = {}

    for uid, user_metrics in per_user.items():
        for idx, m in enumerate(user_metrics, start=1):
            if m.disposition_dei is not None:
                dei_by_sess.setdefault(idx, []).append(abs(m.disposition_dei))
            if m.overconfidence_score is not None:
                ocs_by_sess.setdefault(idx, []).append(m.overconfidence_score)
            if m.loss_aversion_index is not None:
                lai_by_sess.setdefault(idx, []).append(m.loss_aversion_index)

    all_sess_nums = sorted(
        set(dei_by_sess) | set(ocs_by_sess) | set(lai_by_sess)
    )
    rows: list[dict] = []
    for sess_num in all_sess_nums:
        for bias_key, data_dict in [
            ("dei", dei_by_sess),
            ("ocs", ocs_by_sess),
            ("lai", lai_by_sess),
        ]:
            vals = data_dict.get(sess_num, [])
            mean, sd = _mean_sd(vals)
            rows.append({
                "session_number": sess_num,
                "bias": bias_key,
                "mean": mean,
                "sd": sd,
                "n": len(vals),
                "values": list(vals),
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
