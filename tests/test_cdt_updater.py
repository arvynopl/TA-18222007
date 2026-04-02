"""
tests/test_cdt_updater.py — Unit tests for CDT profile updates.

Critical tests:
    - test_ema_convergence:    10 sessions OCS=0.8 → profile approaches 0.8
    - test_stability_stable:   5 similar sessions → stability_index > 0.7
    - test_stability_erratic:  alternating extremes → stability_index < 0.5
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import ALPHA, BETA
from database.models import Base, BiasMetric, CognitiveProfile, User, StockCatalog
from modules.cdt.profile import get_or_create_profile
from modules.cdt.stability import compute_stability_index
from modules.cdt.updater import update_profile


# ---------------------------------------------------------------------------
# In-memory SQLite fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


@pytest.fixture()
def user(db):
    u = User(alias="test_user", experience_level="beginner")
    db.add(u)
    db.flush()
    return u


def _make_metric(db, user_id: int, ocs: float, dei: float = 0.0, lai: float = 1.0) -> BiasMetric:
    """Helper: create and persist a BiasMetric with given scores."""
    m = BiasMetric(
        user_id=user_id,
        session_id=str(uuid.uuid4()),
        overconfidence_score=ocs,
        disposition_pgr=max(dei, 0.0),
        disposition_plr=0.0,
        disposition_dei=dei,
        loss_aversion_index=lai,
    )
    db.add(m)
    db.flush()
    return m


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

def test_get_or_create_returns_default_profile(db, user):
    profile = get_or_create_profile(db, user.id)
    assert profile.session_count == 0
    assert profile.bias_intensity_vector["overconfidence"] == 0.0
    assert profile.bias_intensity_vector["disposition"] == 0.0
    assert profile.bias_intensity_vector["loss_aversion"] == 0.0
    assert profile.risk_preference == 0.0
    assert profile.stability_index == 0.0


def test_get_or_create_returns_existing_profile(db, user):
    p1 = get_or_create_profile(db, user.id)
    p1.session_count = 5
    db.flush()
    p2 = get_or_create_profile(db, user.id)
    assert p2.session_count == 5
    assert p1.id == p2.id


# ---------------------------------------------------------------------------
# EMA update
# ---------------------------------------------------------------------------

def test_first_session_ema_update(db, user):
    """After first session with OCS=0.8, profile.overconfidence = ALPHA × 0.8."""
    metric = _make_metric(db, user.id, ocs=0.8)
    profile = update_profile(db, user.id, metric, metric.session_id)

    expected = ALPHA * 0.8 + (1 - ALPHA) * 0.0
    assert profile.bias_intensity_vector["overconfidence"] == pytest.approx(expected)
    assert profile.session_count == 1


def test_ema_convergence_after_many_sessions(db, user):
    """10 identical sessions with OCS=0.8 → profile approaches 0.8."""
    TARGET = 0.8
    NUM_SESSIONS = 10

    for _ in range(NUM_SESSIONS):
        metric = _make_metric(db, user.id, ocs=TARGET)
        update_profile(db, user.id, metric, metric.session_id)
        db.flush()

    profile = get_or_create_profile(db, user.id)
    # EMA with ALPHA=0.3 converges: value after n steps = T*(1 - (1-ALPHA)^n)
    convergence_error = abs(profile.bias_intensity_vector["overconfidence"] - TARGET)
    assert convergence_error < 0.15, (
        f"After {NUM_SESSIONS} sessions at OCS={TARGET}, expected value near {TARGET}, "
        f"got {profile.bias_intensity_vector['overconfidence']:.4f}"
    )


def test_ema_loss_aversion_normalized(db, user):
    """LAI is normalised to [0,1] as min(LAI/3, 1) before EMA."""
    metric = _make_metric(db, user.id, ocs=0.0, lai=3.0)
    profile = update_profile(db, user.id, metric, metric.session_id)
    # min(3.0/3, 1.0) = 1.0 → ALPHA * 1.0 + (1-ALPHA) * 0.0
    expected = ALPHA * 1.0
    assert profile.bias_intensity_vector["loss_aversion"] == pytest.approx(expected)


def test_session_count_increments(db, user):
    for i in range(3):
        metric = _make_metric(db, user.id, ocs=0.5)
        update_profile(db, user.id, metric, metric.session_id)
    profile = get_or_create_profile(db, user.id)
    assert profile.session_count == 3


# ---------------------------------------------------------------------------
# Stability index
# ---------------------------------------------------------------------------

def test_stability_index_zero_with_single_session(db, user):
    """Single session → insufficient data → stability = 0.0."""
    _make_metric(db, user.id, ocs=0.7)
    si = compute_stability_index(db, user.id)
    assert si == 0.0


def test_stability_stable_sessions(db, user):
    """5 near-identical sessions → stability > 0.7."""
    for _ in range(5):
        _make_metric(db, user.id, ocs=0.75, dei=0.3, lai=2.0)
    si = compute_stability_index(db, user.id)
    assert si > 0.7, f"Expected stability > 0.7, got {si:.4f}"


def test_stability_erratic_sessions(db, user):
    """Alternating extremes → stability < 0.5."""
    for i in range(6):
        ocs = 0.9 if i % 2 == 0 else 0.1
        dei = 0.8 if i % 2 == 0 else -0.8
        lai = 3.0 if i % 2 == 0 else 0.2
        _make_metric(db, user.id, ocs=ocs, dei=dei, lai=lai)
    si = compute_stability_index(db, user.id)
    assert si < 0.5, f"Expected stability < 0.5, got {si:.4f}"
