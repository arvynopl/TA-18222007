"""
tests/test_bias_metrics.py — Unit tests for bias metric formulas.

Critical test scenarios:
    - test_disposition_effect: sells all winners, holds all losers → DEI > 0.5
    - test_overconfidence:      14 trades + portfolio decline → OCS > 0.7
    - test_loss_aversion:       holds losers 3× longer → LAI > 2.0
"""

import pytest

from modules.analytics.bias_metrics import (
    classify_severity,
    compute_disposition_effect,
    compute_loss_aversion_index,
    compute_overconfidence_score,
)
from modules.analytics.features import SessionFeatures


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_features(
    buy_count=0,
    sell_count=0,
    hold_count=0,
    initial_value=10_000_000.0,
    final_value=10_000_000.0,
    realized_trades=None,
    open_positions=None,
):
    f = SessionFeatures(user_id=1, session_id="test-session")
    f.buy_count = buy_count
    f.sell_count = sell_count
    f.hold_count = hold_count
    f.initial_value = initial_value
    f.final_value = final_value
    f.realized_trades = realized_trades or []
    f.open_positions = open_positions or []
    return f


# ---------------------------------------------------------------------------
# Disposition Effect
# ---------------------------------------------------------------------------

def test_disposition_effect_sells_winners_holds_losers():
    """Sells all 5 winners, holds all 3 losers → DEI > 0.5."""
    features = make_features(
        realized_trades=[
            # 5 winning sells
            {"stock_id": "BBCA.JK", "buy_round": 1, "sell_round": 5,
             "buy_price": 8000, "sell_price": 9000, "quantity": 100},
            {"stock_id": "BBCA.JK", "buy_round": 2, "sell_round": 6,
             "buy_price": 7500, "sell_price": 8500, "quantity": 50},
            {"stock_id": "TLKM.JK", "buy_round": 1, "sell_round": 4,
             "buy_price": 3000, "sell_price": 3500, "quantity": 200},
            {"stock_id": "BBRI.JK", "buy_round": 3, "sell_round": 8,
             "buy_price": 4000, "sell_price": 4500, "quantity": 100},
            {"stock_id": "ANTM.JK", "buy_round": 2, "sell_round": 7,
             "buy_price": 2000, "sell_price": 2400, "quantity": 200},
        ],
        open_positions=[
            # 3 losing open positions (paper losses)
            {"stock_id": "GOTO.JK", "quantity": 1000, "avg_price": 80,
             "final_price": 60, "rounds_held": 8, "unrealized_pnl": -20000},
            {"stock_id": "UNVR.JK", "quantity": 100, "avg_price": 2500,
             "final_price": 2000, "rounds_held": 5, "unrealized_pnl": -50000},
            {"stock_id": "TLKM.JK", "quantity": 50, "avg_price": 3200,
             "final_price": 2800, "rounds_held": 7, "unrealized_pnl": -20000},
        ],
    )
    pgr, plr, dei = compute_disposition_effect(features)
    assert dei > 0.5, f"Expected DEI > 0.5, got {dei:.4f} (PGR={pgr:.4f}, PLR={plr:.4f})"
    assert pgr > plr


def test_disposition_effect_holds_winners_sells_losers():
    """Sells all losers, holds all winners → DEI < 0 (reversed disposition)."""
    features = make_features(
        realized_trades=[
            {"stock_id": "GOTO.JK", "buy_round": 1, "sell_round": 5,
             "buy_price": 80, "sell_price": 60, "quantity": 1000},
        ],
        open_positions=[
            {"stock_id": "BBCA.JK", "quantity": 100, "avg_price": 8000,
             "final_price": 9000, "rounds_held": 10, "unrealized_pnl": 100000},
        ],
    )
    pgr, plr, dei = compute_disposition_effect(features)
    assert dei < 0


def test_disposition_effect_no_trades():
    """No realized trades and no open positions → DEI = 0."""
    features = make_features()
    pgr, plr, dei = compute_disposition_effect(features)
    assert pgr == 0.0
    assert plr == 0.0
    assert dei == 0.0


def test_disposition_effect_only_paper_gains():
    """Only paper gains (no sells) → PGR = 0, PLR = 0, DEI = 0."""
    features = make_features(
        open_positions=[
            {"stock_id": "BBCA.JK", "quantity": 100, "avg_price": 8000,
             "final_price": 10000, "rounds_held": 5, "unrealized_pnl": 200000},
        ]
    )
    pgr, plr, dei = compute_disposition_effect(features)
    # PGR = 0 / (0 + 1) = 0, PLR = 0 / (0 + 0) = 0
    assert pgr == 0.0
    assert dei == 0.0


# ---------------------------------------------------------------------------
# Overconfidence Score
# ---------------------------------------------------------------------------

def test_overconfidence_high_frequency_poor_performance():
    """14 trades + portfolio decline → OCS > 0.5 (moderate).

    With new shifted-sigmoid formula:
        raw = (14/14) / 0.85 = 1.176 → OCS = 2*(sigmoid(1.176)-0.5) ≈ 0.529
    """
    features = make_features(
        buy_count=7,
        sell_count=7,
        initial_value=10_000_000.0,
        final_value=8_500_000.0,   # 15% decline
    )
    ocs = compute_overconfidence_score(features)
    assert ocs > 0.5, f"Expected OCS > 0.5, got {ocs:.4f}"


def test_overconfidence_low_frequency_good_performance():
    """Low trading, portfolio grew → OCS should be lower."""
    features = make_features(
        buy_count=2,
        sell_count=1,
        initial_value=10_000_000.0,
        final_value=11_000_000.0,  # 10% gain
    )
    ocs_low = compute_overconfidence_score(features)
    features_high = make_features(
        buy_count=7, sell_count=7,
        initial_value=10_000_000.0, final_value=8_500_000.0,
    )
    ocs_high = compute_overconfidence_score(features_high)
    assert ocs_low < ocs_high


def test_overconfidence_no_trades_returns_low():
    """No trades at all → OCS should be low (sigmoid of near-zero)."""
    features = make_features(buy_count=0, sell_count=0)
    ocs = compute_overconfidence_score(features)
    assert 0.0 <= ocs <= 0.6


def test_ocs_zero_trades_returns_zero():
    """All-hold session (0 trades) → OCS = 0.0 exactly.

    raw = 0 → sigmoid(0) = 0.5 → 2*(0.5-0.5) = 0.0
    """
    features = make_features(buy_count=0, sell_count=0)
    ocs = compute_overconfidence_score(features)
    assert ocs == pytest.approx(0.0), f"Expected OCS ≈ 0.0 for zero trades, got {ocs:.6f}"


def test_ocs_single_buy_returns_near_zero():
    """Single buy (1 trade, perf=1.0) → OCS < 0.05.

    raw = (1/14) / 1.0 = 0.071 → OCS = 2*(sigmoid(0.071)-0.5) ≈ 0.036
    """
    features = make_features(
        buy_count=1,
        sell_count=0,
        initial_value=10_000_000.0,
        final_value=10_000_000.0,
    )
    ocs = compute_overconfidence_score(features)
    assert ocs < 0.05, f"Expected OCS < 0.05 for single buy, got {ocs:.6f}"


def test_overconfidence_bounded_zero_to_one():
    """OCS must always be in [0, 1]."""
    for buy, sell, final in [(0, 0, 10_000_000), (14, 0, 1), (7, 7, 8_000_000)]:
        features = make_features(
            buy_count=buy, sell_count=sell,
            initial_value=10_000_000.0, final_value=float(final),
        )
        ocs = compute_overconfidence_score(features)
        assert 0.0 <= ocs <= 1.0


# ---------------------------------------------------------------------------
# Loss Aversion Index
# ---------------------------------------------------------------------------

def test_loss_aversion_holds_losers_3x_longer():
    """Holds losers avg 6 rounds, winners avg 2 rounds → LAI = 3.0 > 2.0."""
    features = make_features(
        realized_trades=[
            # Winners: sold quickly
            {"stock_id": "BBCA.JK", "buy_round": 1, "sell_round": 3,
             "buy_price": 8000, "sell_price": 9000, "quantity": 100},
            {"stock_id": "TLKM.JK", "buy_round": 2, "sell_round": 4,
             "buy_price": 3000, "sell_price": 3500, "quantity": 200},
            # Losers: held long
            {"stock_id": "GOTO.JK", "buy_round": 1, "sell_round": 7,
             "buy_price": 80, "sell_price": 60, "quantity": 1000},
            {"stock_id": "UNVR.JK", "buy_round": 2, "sell_round": 8,
             "buy_price": 2500, "sell_price": 2000, "quantity": 100},
        ]
    )
    lai = compute_loss_aversion_index(features)
    assert lai > 2.0, f"Expected LAI > 2.0, got {lai:.4f}"


def test_loss_aversion_equal_holds():
    """Holds winners and losers for the same duration → LAI ≈ 1."""
    features = make_features(
        realized_trades=[
            {"stock_id": "BBCA.JK", "buy_round": 1, "sell_round": 5,
             "buy_price": 8000, "sell_price": 9000, "quantity": 100},
            {"stock_id": "GOTO.JK", "buy_round": 1, "sell_round": 5,
             "buy_price": 80, "sell_price": 60, "quantity": 1000},
        ]
    )
    lai = compute_loss_aversion_index(features)
    assert lai == pytest.approx(1.0)


def test_loss_aversion_no_trades_returns_zero():
    """No completed trades → avg_hold_losers=0, avg_hold_winners=0, LAI = 0/1 = 0."""
    features = make_features()
    lai = compute_loss_aversion_index(features)
    assert lai == pytest.approx(0.0)


def test_loss_aversion_only_winners_returns_zero_over_avg():
    """Only winning trades → no loser hold periods → avg_losers = 0 → LAI = 0."""
    features = make_features(
        realized_trades=[
            {"stock_id": "BBCA.JK", "buy_round": 1, "sell_round": 4,
             "buy_price": 8000, "sell_price": 9000, "quantity": 100},
        ]
    )
    lai = compute_loss_aversion_index(features)
    # avg_losers = 0, avg_winners = 3 → LAI = 0/3 = 0
    assert lai == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Severity classifier
# ---------------------------------------------------------------------------

def test_classify_severity_severe():
    assert classify_severity(0.65, 0.5, 0.15) == "severe"


def test_classify_severity_moderate():
    assert classify_severity(0.3, 0.5, 0.15) == "moderate"


def test_classify_severity_none():
    assert classify_severity(0.05, 0.5, 0.15) == "none"


def test_classify_severity_boundary_severe():
    assert classify_severity(0.5, 0.5, 0.15) == "severe"


def test_classify_severity_boundary_moderate():
    assert classify_severity(0.15, 0.5, 0.15) == "moderate"


def test_classify_severity_mild_level():
    """Value between mild_t and moderate_t → 'mild'."""
    assert classify_severity(0.10, 0.5, 0.15, mild_t=0.08) == "mild"


def test_classify_severity_mild_boundary():
    """At exactly mild_t → 'mild'; just below → 'none'."""
    assert classify_severity(0.08, 0.5, 0.15, mild_t=0.08) == "mild"
    assert classify_severity(0.07, 0.5, 0.15, mild_t=0.08) == "none"


def test_classify_severity_mild_not_triggered_without_threshold():
    """Existing 3-arg calls still return 'none' below moderate (no mild path)."""
    assert classify_severity(0.10, 0.5, 0.15) == "none"
