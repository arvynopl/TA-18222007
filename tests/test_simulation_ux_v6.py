"""tests/test_simulation_ux_v6.py — v6 Phase 3 simulation UX behaviours.

Covers:
  * Item 4 — running cash preview helper (`compute_projected_end_round_cash`)
  * Item 5 — historical candlestick trace in `_build_full_chart`
  * Item 6 — reactive confirm-button label helper
"""

from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go
import pytest

from modules.simulation.portfolio import Portfolio
from modules.simulation.ui import (
    ACTION_LABELS, _build_full_chart,
    build_order_button_label, compute_projected_end_round_cash,
)


# ---------------------------------------------------------------------------
# Item 6 — reactive confirm-button label
# ---------------------------------------------------------------------------

def test_action_label_map_expected():
    assert ACTION_LABELS == {"buy": "Beli", "sell": "Jual", "hold": "Tahan"}


@pytest.mark.parametrize(
    "action,ticker,expected",
    [
        ("Beli", "BBCA", "Tambahkan ke Antrean: Beli BBCA"),
        ("Jual", "BBCA", "Tambahkan ke Antrean: Jual BBCA"),
        ("Tahan", "BBCA", "Konfirmasi: Tahan BBCA"),
        ("buy", "TLKM", "Tambahkan ke Antrean: Beli TLKM"),
        ("sell", "TLKM", "Tambahkan ke Antrean: Jual TLKM"),
        ("hold", "TLKM", "Konfirmasi: Tahan TLKM"),
    ],
)
def test_build_order_button_label_is_reactive(action, ticker, expected):
    assert build_order_button_label(action, ticker) == expected


def test_build_order_button_label_flip_updates_immediately():
    """Regression: label must reflect the current action, not a stale one."""
    first = build_order_button_label("Tahan", "BBCA")
    second = build_order_button_label("Beli", "BBCA")
    assert first != second
    assert "Tahan" in first
    assert "Beli" in second


# ---------------------------------------------------------------------------
# Item 4 — cash preview / projected end-round cash
# ---------------------------------------------------------------------------

def test_projected_cash_equals_cash_plus_holdings_at_current_prices():
    p = Portfolio(10_000_000)
    # Buy 100 BBCA at 9000 (cost 900,000 → cash 9,100,000)
    p.buy("BBCA.JK", 100, 9000.0, 1)
    # Current price 9500 → expected projection = 9,100,000 + 100*9500 = 10,050,000
    projected = compute_projected_end_round_cash(p, {"BBCA.JK": 9500.0})
    assert projected == pytest.approx(10_050_000)


def test_projected_cash_uses_avg_price_when_current_missing():
    p = Portfolio(5_000_000)
    p.buy("TLKM.JK", 200, 3000.0, 1)
    # Omit TLKM.JK from current_prices — projection should fall back to avg.
    projected = compute_projected_end_round_cash(p, {})
    assert projected == pytest.approx(5_000_000)


def test_projected_cash_no_positions():
    p = Portfolio(10_000_000)
    assert compute_projected_end_round_cash(p, {}) == pytest.approx(10_000_000)


# ---------------------------------------------------------------------------
# Item 5 — historical window is a Candlestick trace
# ---------------------------------------------------------------------------

_BASE_DATE = date(2024, 1, 1)


def _fake_bar(i: int, up: bool = True) -> dict:
    open_ = 1000.0 + i
    close = open_ + (5 if up else -5)
    return {
        "date": _BASE_DATE + timedelta(days=i),
        "open": open_,
        "high": max(open_, close) + 2,
        "low": min(open_, close) - 2,
        "close": close,
        "volume": 1_000_000,
        "ma_5": open_,
        "ma_20": open_,
    }


def test_historical_window_renders_muted_candlesticks():
    pre_history = [_fake_bar(i, up=(i % 2 == 0)) for i in range(10)]
    window = [_fake_bar(20 + i, up=True) for i in range(14)]

    fig = _build_full_chart("BBCA.JK", pre_history, window, current_round=1)

    candles = [
        t for t in fig.data
        if isinstance(t, go.Candlestick) and t.name == "Riwayat"
    ]
    assert candles, "Pre-window history must render as a Candlestick trace named 'Riwayat'"
    # Muted appearance — must be ≤ 0.5 opacity to read as background context.
    assert (candles[0].opacity or 1.0) <= 0.5


def test_historical_candle_colors_match_light_theme():
    from modules.utils.ui_helpers import COLOR_GAIN, COLOR_LOSS

    pre_history = [_fake_bar(i, up=(i % 2 == 0)) for i in range(10)]
    window = [_fake_bar(20 + i) for i in range(14)]
    fig = _build_full_chart("BBCA.JK", pre_history, window, current_round=1)

    hist = next(
        t for t in fig.data
        if isinstance(t, go.Candlestick) and t.name == "Riwayat"
    )
    assert hist.increasing.fillcolor == COLOR_GAIN
    assert hist.decreasing.fillcolor == COLOR_LOSS
