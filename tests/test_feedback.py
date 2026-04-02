"""
tests/test_feedback.py — Unit tests for feedback template generation.

Critical tests:
    - test_severe_dei_selects_correct_template
    - test_none_severity_no_bias_text
    - test_template_slots_filled
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, BiasMetric, CognitiveProfile, FeedbackHistory, User
from modules.analytics.bias_metrics import classify_severity
from modules.cdt.profile import get_or_create_profile
from modules.feedback.generator import generate_feedback, get_session_feedback
from modules.feedback.templates import TEMPLATES


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


@pytest.fixture()
def user(db):
    u = User(alias="feedback_user", experience_level="beginner")
    db.add(u)
    db.flush()
    return u


def _make_metric(db, user_id, ocs=0.0, dei=0.0, lai=1.0):
    sid = str(uuid.uuid4())
    m = BiasMetric(
        user_id=user_id,
        session_id=sid,
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
# Template structure validation
# ---------------------------------------------------------------------------

def test_templates_have_all_biases():
    assert "disposition_effect" in TEMPLATES
    assert "overconfidence" in TEMPLATES
    assert "loss_aversion" in TEMPLATES


def test_templates_have_all_severity_levels():
    for bias in ["disposition_effect", "overconfidence", "loss_aversion"]:
        for level in ["mild", "moderate", "severe"]:
            assert level in TEMPLATES[bias], f"Missing {bias}/{level}"
            assert "explanation" in TEMPLATES[bias][level]
            assert "recommendation" in TEMPLATES[bias][level]


# ---------------------------------------------------------------------------
# Severity classification → template selection
# ---------------------------------------------------------------------------

def test_severe_dei_selects_correct_template(db, user):
    """DEI = 0.65 → severity = 'severe' → explanation contains severe template text."""
    metric = _make_metric(db, user.id, dei=0.65)
    profile = get_or_create_profile(db, user.id)

    feedbacks = generate_feedback(
        db_session=db,
        user_id=user.id,
        session_id=metric.session_id,
        bias_metric=metric,
        profile=profile,
        realized_trades=[
            {"stock_id": "BBCA.JK", "buy_round": 1, "sell_round": 5,
             "buy_price": 8000, "sell_price": 9000, "quantity": 100},
        ],
        open_positions=[
            {"stock_id": "GOTO.JK", "quantity": 100, "avg_price": 80,
             "final_price": 60, "rounds_held": 8, "unrealized_pnl": -2000},
        ],
    )

    disp_fb = next(f for f in feedbacks if f.bias_type == "disposition_effect")
    assert disp_fb.severity == "severe"
    # Check explanation was rendered (not still a template placeholder)
    assert "{dei" not in disp_fb.explanation_text
    assert "{pgr" not in disp_fb.explanation_text


def test_severe_overconfidence_selects_correct_template(db, user):
    """OCS = 0.85 → severity = 'severe'."""
    metric = _make_metric(db, user.id, ocs=0.85)
    profile = get_or_create_profile(db, user.id)

    feedbacks = generate_feedback(db, user.id, metric.session_id, metric, profile)
    oc_fb = next(f for f in feedbacks if f.bias_type == "overconfidence")
    assert oc_fb.severity == "severe"


def test_none_severity_produces_positive_feedback(db, user):
    """DEI = 0.03 (below mild threshold) → severity = 'none', positive message."""
    metric = _make_metric(db, user.id, dei=0.03, ocs=0.1, lai=0.8)
    profile = get_or_create_profile(db, user.id)

    feedbacks = generate_feedback(db, user.id, metric.session_id, metric, profile)

    for fb in feedbacks:
        assert fb.severity == "none"
        # Should contain a positive/neutral message
        assert fb.explanation_text is not None
        assert len(fb.explanation_text) > 0


def test_generates_three_feedback_records(db, user):
    """Always generates exactly 3 FeedbackHistory rows (one per bias type)."""
    metric = _make_metric(db, user.id, ocs=0.5, dei=0.3, lai=1.8)
    profile = get_or_create_profile(db, user.id)

    feedbacks = generate_feedback(db, user.id, metric.session_id, metric, profile)
    assert len(feedbacks) == 3

    bias_types = {f.bias_type for f in feedbacks}
    assert "disposition_effect" in bias_types
    assert "overconfidence" in bias_types
    assert "loss_aversion" in bias_types


def test_template_slots_filled_with_actual_values(db, user):
    """Generated text must not contain raw format placeholders like {ocs}."""
    metric = _make_metric(db, user.id, ocs=0.82, dei=0.6, lai=2.5)
    profile = get_or_create_profile(db, user.id)

    feedbacks = generate_feedback(db, user.id, metric.session_id, metric, profile)

    for fb in feedbacks:
        if fb.explanation_text:
            assert "{" not in fb.explanation_text, (
                f"Unfilled placeholder in {fb.bias_type} explanation: {fb.explanation_text}"
            )
        if fb.recommendation_text:
            assert "{" not in fb.recommendation_text


def test_get_session_feedback_retrieves_records(db, user):
    metric = _make_metric(db, user.id, ocs=0.6)
    profile = get_or_create_profile(db, user.id)

    generate_feedback(db, user.id, metric.session_id, metric, profile)
    retrieved = get_session_feedback(db, user.id, metric.session_id)

    assert len(retrieved) == 3


def test_loss_aversion_severe_threshold(db, user):
    """LAI = 2.5 → severity = 'severe'."""
    metric = _make_metric(db, user.id, lai=2.5)
    profile = get_or_create_profile(db, user.id)

    feedbacks = generate_feedback(db, user.id, metric.session_id, metric, profile)
    la_fb = next(f for f in feedbacks if f.bias_type == "loss_aversion")
    assert la_fb.severity == "severe"


def test_classify_severity_dei():
    assert classify_severity(0.65, 0.5, 0.15) == "severe"
    assert classify_severity(0.25, 0.5, 0.15) == "moderate"
    assert classify_severity(0.05, 0.5, 0.15) == "none"
