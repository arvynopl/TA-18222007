"""
tests/test_research_export.py — Tests for modules/utils/research_export.py.

Uses the shared in-memory ``db`` fixture from conftest.py. Seeds users,
onboarding surveys, bias metrics, CDT snapshots, and consent rows directly
without invoking the full simulation pipeline so the tests stay fast and
focused on the export logic.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from database.models import (
    BiasMetric, CdtSnapshot, CognitiveProfile, ConsentLog,
    OnboardingSurvey, User, UserAction, UserProfile,
)
from modules.utils.research_export import (
    export_all_sessions_csv,
    export_all_users_csv,
    export_cdt_snapshots_csv,
    get_cohort_summary,
    load_model_performance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_user(db, username: str) -> User:
    u = User(username=username, alias=username, experience_level="beginner")
    db.add(u)
    db.flush()
    return u


def _make_profile(db, user_id: int) -> UserProfile:
    prof = UserProfile(
        user_id=user_id,
        full_name=f"User {user_id}",
        age=25,
        gender="laki-laki",
        risk_profile="moderat",
        investing_capability="pemula",
    )
    db.add(prof)
    db.flush()
    return prof


def _make_onboarding(db, user_id: int) -> OnboardingSurvey:
    onb = OnboardingSurvey(
        user_id=user_id,
        dei_q1=4, dei_q2=3, dei_q3=4,
        ocs_q1=2, ocs_q2=3, ocs_q3=2,
        lai_q1=5, lai_q2=4, lai_q3=5,
    )
    db.add(onb)
    db.flush()
    return onb


def _make_metric(
    db, user_id: int, computed_at: datetime,
    *, dei: float = 0.2, ocs: float = 0.4, lai: float = 1.5,
) -> BiasMetric:
    sid = str(uuid.uuid4())
    m = BiasMetric(
        user_id=user_id,
        session_id=sid,
        overconfidence_score=ocs,
        disposition_pgr=0.6,
        disposition_plr=0.3,
        disposition_dei=dei,
        loss_aversion_index=lai,
        computed_at=computed_at,
    )
    db.add(m)
    db.flush()
    return m


def _make_cdt(db, user_id: int) -> CognitiveProfile:
    cdt = CognitiveProfile(
        user_id=user_id,
        bias_intensity_vector={
            "overconfidence": 0.4,
            "disposition": 0.2,
            "loss_aversion": 0.5,
        },
        risk_preference=0.4,
        stability_index=0.7,
        session_count=2,
        last_updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db.add(cdt)
    db.flush()
    return cdt


# ---------------------------------------------------------------------------
# Tests — get_cohort_summary
# ---------------------------------------------------------------------------
def test_get_cohort_summary_empty(db):
    summary = get_cohort_summary(db)
    assert summary["total_users"] == 0
    assert summary["total_sessions"] == 0
    assert summary["users_with_consent"] == 0
    assert summary["users_with_survey"] == 0
    assert summary["users_with_min_3_sessions"] == 0
    assert summary["completion_rate"] == 0.0
    assert summary["mean_dei"] == 0.0
    assert summary["sd_dei"] == 0.0
    assert summary["mean_stability_index"] == 0.0


def test_get_cohort_summary_basic(db):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    u1 = _make_user(db, "alpha")
    u2 = _make_user(db, "beta")
    u3 = _make_user(db, "gamma")
    _make_metric(db, u1.id, base, dei=0.1, ocs=0.2, lai=1.0)
    _make_metric(db, u2.id, base, dei=0.2, ocs=0.4, lai=1.5)
    _make_metric(db, u2.id, base + timedelta(hours=1), dei=0.3, ocs=0.5, lai=1.8)
    _make_metric(db, u3.id, base, dei=0.4, ocs=0.3, lai=2.0)
    _make_metric(db, u3.id, base + timedelta(hours=1), dei=0.2, ocs=0.3, lai=1.5)
    _make_metric(db, u3.id, base + timedelta(hours=2), dei=0.3, ocs=0.4, lai=1.7)

    summary = get_cohort_summary(db)
    assert summary["total_users"] == 3
    assert summary["total_sessions"] == 6
    assert summary["users_with_min_3_sessions"] == 1
    assert summary["completion_rate"] == pytest.approx(1 / 3, rel=1e-3)
    expected_mean_dei = (0.1 + 0.2 + 0.3 + 0.4 + 0.2 + 0.3) / 6
    assert summary["mean_dei"] == pytest.approx(expected_mean_dei, abs=1e-3)


# ---------------------------------------------------------------------------
# Tests — export_all_users_csv
# ---------------------------------------------------------------------------
def test_export_all_users_csv_columns(db):
    u = _make_user(db, "schema_check")
    _make_profile(db, u.id)
    rows = export_all_users_csv(db)
    assert len(rows) == 1
    expected = {
        "user_id", "username", "age", "gender", "risk_profile",
        "investing_capability", "consent_given", "registered_at",
        "session_count",
        "onboarding_dei_q1", "onboarding_dei_q2", "onboarding_dei_q3",
        "onboarding_ocs_q1", "onboarding_ocs_q2", "onboarding_ocs_q3",
        "onboarding_lai_q1", "onboarding_lai_q2", "onboarding_lai_q3",
        "survey_risk_tolerance", "survey_loss_sensitivity",
        "survey_trading_frequency", "survey_holding_behavior",
        "cdt_overconfidence", "cdt_disposition", "cdt_loss_aversion",
        "risk_preference", "stability_index", "last_updated_at",
    }
    assert expected.issubset(set(rows[0].keys()))


def test_export_all_users_csv_includes_onboarding(db):
    u = _make_user(db, "with_onboard")
    _make_profile(db, u.id)
    _make_onboarding(db, u.id)
    db.add(ConsentLog(user_id=u.id, consent_given=True))
    db.flush()

    rows = export_all_users_csv(db)
    assert len(rows) == 1
    row = rows[0]
    assert row["onboarding_dei_q1"] == 4
    assert row["onboarding_dei_q2"] == 3
    assert row["onboarding_dei_q3"] == 4
    assert row["onboarding_ocs_q1"] == 2
    assert row["onboarding_ocs_q2"] == 3
    assert row["onboarding_ocs_q3"] == 2
    assert row["onboarding_lai_q1"] == 5
    assert row["onboarding_lai_q2"] == 4
    assert row["onboarding_lai_q3"] == 5
    assert row["consent_given"] is True


def test_export_all_users_csv_handles_missing_survey(db):
    u = _make_user(db, "no_survey")
    rows = export_all_users_csv(db)
    assert len(rows) == 1
    row = rows[0]
    assert row["onboarding_dei_q1"] is None
    assert row["onboarding_ocs_q2"] is None
    assert row["onboarding_lai_q3"] is None
    assert row["survey_risk_tolerance"] is None
    assert row["consent_given"] is False
    assert row["cdt_overconfidence"] is None


# ---------------------------------------------------------------------------
# Tests — export_all_sessions_csv
# ---------------------------------------------------------------------------
def test_export_all_sessions_csv_session_num_ordering(db):
    base = datetime(2026, 2, 1, tzinfo=timezone.utc)
    u = _make_user(db, "sess_order")
    m1 = _make_metric(db, u.id, base + timedelta(hours=2))
    m2 = _make_metric(db, u.id, base + timedelta(hours=0))
    m3 = _make_metric(db, u.id, base + timedelta(hours=1))

    rows = export_all_sessions_csv(db)
    assert [r["session_num"] for r in rows] == [1, 2, 3]
    assert rows[0]["session_id"] == m2.session_id  # earliest first
    assert rows[1]["session_id"] == m3.session_id
    assert rows[2]["session_id"] == m1.session_id


def test_export_all_sessions_csv_action_count(db):
    """action_count column reflects the number of UserAction rows in the session."""
    base = datetime(2026, 3, 1, tzinfo=timezone.utc)
    u = _make_user(db, "sess_actions")
    m = _make_metric(db, u.id, base)

    snap = db.query(__import__("database.models", fromlist=["MarketSnapshot"]).MarketSnapshot).first()
    for _ in range(5):
        db.add(UserAction(
            user_id=u.id, session_id=m.session_id, scenario_round=1,
            stock_id=snap.stock_id, snapshot_id=snap.id,
            action_type="hold", quantity=0, action_value=0.0,
            response_time_ms=100,
        ))
    db.flush()

    rows = export_all_sessions_csv(db)
    assert rows[0]["action_count"] == 5


# ---------------------------------------------------------------------------
# Tests — export_cdt_snapshots_csv
# ---------------------------------------------------------------------------
def test_export_cdt_snapshots_csv_ordering(db):
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    u_a = _make_user(db, "snap_a")
    u_b = _make_user(db, "snap_b")
    # Insert in a non-sorted order to verify ORDER BY clauses.
    for uid, sn in [
        (u_b.id, 2), (u_a.id, 2), (u_b.id, 1), (u_a.id, 1), (u_a.id, 3),
    ]:
        db.add(CdtSnapshot(
            user_id=uid,
            session_id=str(uuid.uuid4()),
            session_number=sn,
            cdt_overconfidence=0.1 * sn,
            cdt_disposition=0.05 * sn,
            cdt_loss_aversion=0.2 * sn,
            cdt_risk_preference=0.3,
            cdt_stability_index=0.5,
            snapshotted_at=base + timedelta(hours=sn),
        ))
    db.flush()

    rows = export_cdt_snapshots_csv(db)
    keys = [(r["user_id"], r["session_number"]) for r in rows]
    assert keys == [
        (u_a.id, 1), (u_a.id, 2), (u_a.id, 3),
        (u_b.id, 1), (u_b.id, 2),
    ]


# ---------------------------------------------------------------------------
# Tests — load_model_performance
# ---------------------------------------------------------------------------
def test_load_model_performance_missing_dir(tmp_path):
    perf = load_model_performance(tmp_path / "does-not-exist")
    assert perf["available"] is False
    assert perf["summary"] is None
    assert perf["classification_report"] is None
    assert perf["feature_importance_path"] is None
    assert perf["decision_tree_path"] is None
    assert perf["generated_at"] is None


def test_load_model_performance_with_files(tmp_path):
    summary_payload = {
        "generated_at": "2026-04-23T19:41:57.334641+00:00",
        "overall_accuracy": 0.95,
        "n_training_samples": 50,
        "used_synthetic_data": False,
    }
    (tmp_path / "ml_summary.json").write_text(
        json.dumps(summary_payload), encoding="utf-8",
    )
    (tmp_path / "ml_classification_report.csv").write_text(
        "kelas,precision,recall,f1_score,support\n"
        "Tidak Ada Bias,1.0,1.0,1.0,5\n"
        "Rata-rata Makro,0.98,0.97,0.97,5\n",
        encoding="utf-8",
    )
    (tmp_path / "ml_feature_importance.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "ml_decision_tree.png").write_bytes(b"\x89PNG fake")

    perf = load_model_performance(tmp_path)
    assert perf["available"] is True
    assert perf["summary"]["overall_accuracy"] == 0.95
    assert perf["generated_at"] == summary_payload["generated_at"]
    assert isinstance(perf["classification_report"], list)
    assert perf["classification_report"][0]["kelas"] == "Tidak Ada Bias"
    assert perf["feature_importance_path"].endswith("ml_feature_importance.png")
    assert perf["decision_tree_path"].endswith("ml_decision_tree.png")
