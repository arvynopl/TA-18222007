"""
modules/analytics/features.py — Session feature extraction pipeline.

Transforms raw UserAction rows into a structured SessionFeatures dataclass
that the bias-metrics module consumes.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from config import INITIAL_CAPITAL, ROUNDS_PER_SESSION
from database.models import MarketSnapshot, UserAction


@dataclass
class SessionFeatures:
    """All features needed to compute the three bias metrics for one session.

    Attributes:
        user_id:         User identifier.
        session_id:      UUID string for the session.
        buy_count:       Total buy actions (quantity > 0).
        sell_count:      Total sell actions (quantity > 0).
        hold_count:      Total hold / zero-quantity actions.
        initial_value:   Portfolio value at session start (always INITIAL_CAPITAL).
        final_value:     Portfolio value at session end (cash + remaining holdings).
        realized_trades: List of dicts describing completed buy→sell round-trips.
                         Keys: stock_id, buy_round, sell_round, buy_price,
                               sell_price, quantity.
        open_positions:  List of dicts for holdings still open at session end.
                         Keys: stock_id, quantity, avg_price, final_price,
                               rounds_held.
        response_times:  Response times in milliseconds per action.
    """

    user_id: int
    session_id: str
    buy_count: int = 0
    sell_count: int = 0
    hold_count: int = 0
    initial_value: float = INITIAL_CAPITAL
    final_value: float = INITIAL_CAPITAL
    realized_trades: list = field(default_factory=list)
    open_positions: list = field(default_factory=list)
    response_times: list = field(default_factory=list)


def extract_session_features(
    db_session: Session, user_id: int, session_id: str
) -> SessionFeatures:
    """Build a SessionFeatures object from the database for a completed session.

    The function reconstructs portfolio state by replaying UserAction rows in
    round order, tracking cost basis and open positions, then computing the
    final portfolio value from the last available snapshot prices.

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user whose session to analyse.
        session_id: UUID string of the completed session.

    Returns:
        Populated SessionFeatures dataclass.
    """
    actions = (
        db_session.query(UserAction)
        .filter_by(user_id=user_id, session_id=session_id)
        .order_by(UserAction.scenario_round, UserAction.timestamp)
        .all()
    )

    features = SessionFeatures(user_id=user_id, session_id=session_id)
    features.initial_value = INITIAL_CAPITAL

    cash = INITIAL_CAPITAL
    # holdings: stock_id → {quantity, avg_price, buy_round}
    holdings: dict[str, dict] = {}
    realized_trades: list[dict] = []
    response_times: list[int] = []

    # Snapshot prices used for final valuation: {snapshot_id: close}
    snap_prices: dict[int, float] = {}

    # Pass 1: replay trades chronologically
    for action in actions:
        response_times.append(action.response_time_ms)

        # Cache snapshot price
        if action.snapshot_id not in snap_prices:
            snap = db_session.get(MarketSnapshot, action.snapshot_id)
            if snap:
                snap_prices[action.snapshot_id] = snap.close

        price = snap_prices.get(action.snapshot_id, 0.0)

        if action.action_type == "buy" and action.quantity > 0:
            features.buy_count += 1
            cost = action.quantity * price
            cash -= cost
            sid = action.stock_id
            if sid in holdings:
                h = holdings[sid]
                total_qty = h["quantity"] + action.quantity
                h["avg_price"] = (
                    h["avg_price"] * h["quantity"] + price * action.quantity
                ) / total_qty
                h["quantity"] = total_qty
            else:
                holdings[sid] = {
                    "quantity": action.quantity,
                    "avg_price": price,
                    "buy_round": action.scenario_round,
                }

        elif action.action_type == "sell" and action.quantity > 0:
            features.sell_count += 1
            sid = action.stock_id
            if sid in holdings:
                h = holdings[sid]
                proceeds = action.quantity * price
                cash += proceeds
                realized_trades.append({
                    "stock_id": sid,
                    "buy_round": h["buy_round"],
                    "sell_round": action.scenario_round,
                    "buy_price": h["avg_price"],
                    "sell_price": price,
                    "quantity": action.quantity,
                })
                h["quantity"] -= action.quantity
                if h["quantity"] <= 0:
                    del holdings[sid]
        else:
            features.hold_count += 1

    # Pass 2: final snapshot prices for open positions
    # Use the last-round snapshot for each remaining holding
    last_round = ROUNDS_PER_SESSION
    last_round_actions = [a for a in actions if a.scenario_round == last_round]
    last_prices: dict[str, float] = {}
    for a in last_round_actions:
        p = snap_prices.get(a.snapshot_id)
        if p:
            last_prices[a.stock_id] = p

    open_positions: list[dict] = []
    for sid, h in holdings.items():
        final_price = last_prices.get(sid, h["avg_price"])
        open_positions.append({
            "stock_id": sid,
            "quantity": h["quantity"],
            "avg_price": h["avg_price"],
            "final_price": final_price,
            "rounds_held": last_round - h["buy_round"],
            "unrealized_pnl": (final_price - h["avg_price"]) * h["quantity"],
        })

    # Final portfolio value
    market_value = sum(
        p["quantity"] * p["final_price"] for p in open_positions
    )
    features.final_value = cash + market_value
    features.realized_trades = realized_trades
    features.open_positions = open_positions
    features.response_times = response_times

    return features
