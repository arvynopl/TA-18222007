"""
tests/test_integration.py — End-to-end integration test.

Programmatically creates a user, logs 14 rounds of actions for 6 stocks,
then verifies the full pipeline: features → bias metrics → CDT update →
feedback generation, checking all DB records exist with valid values.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import (
    Base, BiasMetric, CognitiveProfile, FeedbackHistory,
    MarketSnapshot, StockCatalog, User, UserAction,
)
from modules.analytics.bias_metrics import compute_and_save_metrics
from modules.analytics.features import extract_session_features
from modules.cdt.updater import update_profile
from modules.feedback.generator import generate_feedback
from modules.logging_engine.logger import log_action


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STOCKS = [
    ("BBCA.JK", "BBCA", "Finance", "low"),
    ("TLKM.JK", "TLKM", "Telecom", "low_medium"),
    ("ANTM.JK", "ANTM", "Mining", "high"),
    ("GOTO.JK", "GOTO", "Technology", "high"),
    ("UNVR.JK", "UNVR", "Consumer", "medium"),
    ("BBRI.JK", "BBRI", "Finance", "medium"),
]

PRICES = {
    "BBCA.JK": 9000.0,
    "TLKM.JK": 3000.0,
    "ANTM.JK": 2000.0,
    "GOTO.JK": 70.0,
    "UNVR.JK": 2000.0,
    "BBRI.JK": 4000.0,
}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()

    # Seed stocks
    for stock_id, ticker, sector, vol_class in STOCKS:
        s = StockCatalog(
            stock_id=stock_id, ticker=ticker, name=f"{ticker} Corp",
            sector=sector, volatility_class=vol_class, bias_role="test",
        )
        sess.add(s)
    sess.flush()

    # Seed 20 snapshots per stock (more than 14 rounds needed)
    base_date = date(2024, 4, 2)
    for stock_id, _, _, _ in STOCKS:
        price = PRICES[stock_id]
        for day in range(20):
            snap = MarketSnapshot(
                stock_id=stock_id,
                date=base_date + timedelta(days=day),
                open=price, high=price * 1.01, low=price * 0.99,
                close=price, volume=1_000_000,
                ma_5=price, ma_20=price, rsi_14=50.0,
                volatility_20d=0.02, trend="neutral", daily_return=0.0,
            )
            sess.add(snap)
    sess.flush()

    yield sess
    sess.close()


@pytest.fixture()
def user(db):
    u = User(alias="integration_user", experience_level="beginner")
    db.add(u)
    db.flush()
    return u


def _get_snapshot(db, stock_id: str, round_num: int) -> MarketSnapshot:
    """Fetch snapshot for stock at round_num (1-indexed)."""
    base_date = date(2024, 4, 2)
    target_date = base_date + timedelta(days=round_num - 1)
    return (
        db.query(MarketSnapshot)
        .filter_by(stock_id=stock_id, date=target_date)
        .first()
    )


# ---------------------------------------------------------------------------
# Helpers to simulate scripted sessions
# ---------------------------------------------------------------------------

def _log_full_session(db, user_id: int, session_id: str, buy_stocks=None, sell_stocks=None):
    """
    Log 14 rounds × 6 stocks = 84 UserActions.

    buy_stocks:  list of stock_ids to buy in round 1.
    sell_stocks: list of stock_ids to sell in round 14 (if previously bought).
    """
    buy_stocks = buy_stocks or []
    sell_stocks = sell_stocks or []
    bought_qty: dict[str, int] = {}

    for rnd in range(1, 15):
        for stock_id, _, _, _ in STOCKS:
            snap = _get_snapshot(db, stock_id, rnd)
            if snap is None:
                continue

            if rnd == 1 and stock_id in buy_stocks:
                qty = 10
                action_type = "buy"
                bought_qty[stock_id] = qty
                action_val = qty * snap.close
            elif rnd == 14 and stock_id in sell_stocks and stock_id in bought_qty:
                qty = bought_qty[stock_id]
                action_type = "sell"
                action_val = qty * snap.close
            else:
                qty = 0
                action_type = "hold"
                action_val = 0.0

            log_action(
                session=db,
                user_id=user_id,
                session_id=session_id,
                scenario_round=rnd,
                stock_id=stock_id,
                snapshot_id=snap.id,
                action_type=action_type,
                quantity=qty,
                action_value=action_val,
                response_time_ms=500,
            )
    db.flush()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_full_pipeline_creates_all_records(db, user):
    """Full session: log → compute metrics → update CDT → generate feedback."""
    session_id = str(uuid.uuid4())

    # 1. Log 14 rounds
    _log_full_session(
        db, user.id, session_id,
        buy_stocks=["BBCA.JK", "ANTM.JK"],
        sell_stocks=["BBCA.JK"],  # sell winner, hold loser
    )

    # Verify actions logged
    action_count = db.query(UserAction).filter_by(
        user_id=user.id, session_id=session_id
    ).count()
    assert action_count == 14 * 6, f"Expected 84 actions, got {action_count}"

    # 2. Compute bias metrics
    metric = compute_and_save_metrics(db, user.id, session_id)
    assert metric.id is not None
    assert 0.0 <= (metric.overconfidence_score or 0.0) <= 1.0
    assert metric.disposition_dei is not None
    assert metric.loss_aversion_index is not None

    # 3. Update CDT profile
    profile = update_profile(db, user.id, metric, session_id)
    assert profile.session_count == 1
    assert 0.0 <= profile.risk_preference <= 1.0
    bv = profile.bias_intensity_vector
    assert "overconfidence" in bv
    assert "disposition" in bv
    assert "loss_aversion" in bv

    # 4. Generate feedback
    features = extract_session_features(db, user.id, session_id)
    feedbacks = generate_feedback(
        db_session=db,
        user_id=user.id,
        session_id=session_id,
        bias_metric=metric,
        profile=profile,
        realized_trades=features.realized_trades,
        open_positions=features.open_positions,
    )
    assert len(feedbacks) == 3, f"Expected 3 feedback records, got {len(feedbacks)}"

    # Verify all feedback rows in DB
    fb_count = db.query(FeedbackHistory).filter_by(
        user_id=user.id, session_id=session_id
    ).count()
    assert fb_count == 3


def test_three_sessions_ema_convergence(db, user):
    """Three sessions update CDT profile; session_count = 3 after all."""
    for _ in range(3):
        sid = str(uuid.uuid4())
        _log_full_session(db, user.id, sid)
        metric = compute_and_save_metrics(db, user.id, sid)
        features = extract_session_features(db, user.id, sid)
        profile = update_profile(db, user.id, metric, sid)
        generate_feedback(db, user.id, sid, metric, profile,
                          features.realized_trades, features.open_positions)

    from modules.cdt.profile import get_or_create_profile
    profile = get_or_create_profile(db, user.id)
    assert profile.session_count == 3

    total_fb = db.query(FeedbackHistory).filter_by(user_id=user.id).count()
    assert total_fb == 9  # 3 sessions × 3 bias types


def test_bias_metric_values_in_valid_range(db, user):
    """Computed bias metrics must be within expected value ranges."""
    sid = str(uuid.uuid4())
    _log_full_session(db, user.id, sid)
    metric = compute_and_save_metrics(db, user.id, sid)

    assert 0.0 <= (metric.overconfidence_score or 0.0) <= 1.0
    assert -1.0 <= (metric.disposition_dei or 0.0) <= 1.0
    assert 0.0 <= (metric.disposition_pgr or 0.0) <= 1.0
    assert 0.0 <= (metric.disposition_plr or 0.0) <= 1.0
    assert (metric.loss_aversion_index or 0.0) >= 0.0
