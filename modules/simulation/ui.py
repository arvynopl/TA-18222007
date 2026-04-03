"""
modules/simulation/ui.py — Streamlit simulation UI page.

Renders the 14-round investment simulation, logs all user actions, and
triggers the full analytics + CDT + feedback pipeline after round 14.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from config import INITIAL_CAPITAL, ROUNDS_PER_SESSION
from database.connection import get_session
from database.models import StockCatalog, UserAction
from modules.analytics.bias_metrics import compute_and_save_metrics
from modules.analytics.features import extract_session_features
from modules.cdt.updater import update_profile
from modules.feedback.generator import generate_feedback
from modules.logging_engine.logger import log_action
from modules.simulation.engine import SimulationEngine
from modules.simulation.portfolio import Portfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_rupiah(value: float) -> str:
    """Format a float as Indonesian Rupiah string."""
    return f"Rp {value:,.0f}"


def _build_price_chart(
    stock_id: str,
    price_history: list[float],
    current_round: int,
    ma5_history: list[float] | None = None,
    ma20_history: list[float] | None = None,
) -> go.Figure:
    """Build a compact Plotly line chart showing price history up to current round.

    Optionally overlays MA5 and MA20 moving average traces.
    """
    rounds = list(range(1, current_round + 1))
    prices = price_history[:current_round]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rounds, y=prices, mode="lines+markers",
        line=dict(color="#1f77b4", width=2),
        marker=dict(size=5),
        name=stock_id,
    ))
    if ma5_history:
        fig.add_trace(go.Scatter(
            x=rounds, y=ma5_history[:current_round],
            mode="lines", name="MA5",
            line=dict(color="#ff7f0e", width=1, dash="dash"),
        ))
    if ma20_history:
        fig.add_trace(go.Scatter(
            x=rounds, y=ma20_history[:current_round],
            mode="lines", name="MA20",
            line=dict(color="#2ca02c", width=1, dash="dot"),
        ))
    has_ma = bool(ma5_history or ma20_history)
    fig.update_layout(
        height=150, margin=dict(l=0, r=0, t=20, b=20),
        xaxis_title=None, yaxis_title=None,
        showlegend=has_ma,
        legend=dict(orientation="h", y=-0.4, font=dict(size=10)) if has_ma else {},
        xaxis=dict(tickmode="linear", dtick=1),
    )
    return fig


# ---------------------------------------------------------------------------
# Session initialisation
# ---------------------------------------------------------------------------

def init_simulation_session() -> None:
    """Initialise Streamlit session state for a new simulation session."""
    if "sim_session_id" not in st.session_state:
        st.session_state["sim_session_id"] = str(uuid.uuid4())

    if "sim_portfolio" not in st.session_state:
        st.session_state["sim_portfolio"] = Portfolio(INITIAL_CAPITAL)

    if "sim_engine" not in st.session_state:
        user_id = st.session_state.get("user_id")
        session_id = st.session_state["sim_session_id"]
        with get_session() as sess:
            engine = SimulationEngine(user_id, session_id, sess)
            # Store window data (snapshots) in session state so we don't keep
            # a live DB session across Streamlit reruns
            st.session_state["sim_window"] = {
                sid: [
                    {
                        "id": snap.id,
                        "stock_id": snap.stock_id,
                        "date": snap.date,
                        "open": snap.open,
                        "high": snap.high,
                        "low": snap.low,
                        "close": snap.close,
                        "volume": snap.volume,
                        "ma_5": snap.ma_5,
                        "ma_20": snap.ma_20,
                        "rsi_14": snap.rsi_14,
                        "trend": snap.trend,
                        "daily_return": snap.daily_return,
                    }
                    for snap in snaps
                ]
                for sid, snaps in engine._window.items()
            }
            st.session_state["sim_stock_ids"] = engine.stock_ids

    if "sim_current_round" not in st.session_state:
        st.session_state["sim_current_round"] = 1

    if "sim_round_start_time" not in st.session_state:
        st.session_state["sim_round_start_time"] = time.time()

    if "sim_complete" not in st.session_state:
        st.session_state["sim_complete"] = False

    if "sim_submitted_round" not in st.session_state:
        st.session_state["sim_submitted_round"] = 0

    if "stock_metadata" not in st.session_state:
        with get_session() as sess:
            stocks = sess.query(StockCatalog).all()
            st.session_state["stock_metadata"] = {
                s.stock_id: {"name": s.name, "sector": s.sector}
                for s in stocks
            }


def reset_simulation() -> None:
    """Clear all simulation-related state keys to start fresh."""
    for key in [
        "sim_session_id", "sim_portfolio", "sim_engine", "sim_window",
        "sim_stock_ids", "sim_current_round", "sim_round_start_time", "sim_complete",
        "sim_submitted_round", "stock_metadata",
    ]:
        st.session_state.pop(key, None)


# ---------------------------------------------------------------------------
# Post-session pipeline
# ---------------------------------------------------------------------------

def _run_post_session_pipeline(user_id: int, session_id: str) -> None:
    """Trigger analytics → CDT update → feedback generation after session ends."""
    with get_session() as sess:
        # 1. Compute bias metrics
        bias_metric = compute_and_save_metrics(sess, user_id, session_id)

        # 2. Extract features for feedback slot-filling
        features = extract_session_features(sess, user_id, session_id)

        # 3. Update CDT profile
        profile = update_profile(sess, user_id, bias_metric, session_id)

        # 4. Generate feedback
        generate_feedback(
            db_session=sess,
            user_id=user_id,
            session_id=session_id,
            bias_metric=bias_metric,
            profile=profile,
            realized_trades=features.realized_trades,
            open_positions=features.open_positions,
        )


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_simulation_page() -> None:
    """Render the simulation UI page (called from app.py)."""
    st.title("Simulasi Investasi")

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.warning("Silakan login terlebih dahulu di halaman Beranda.")
        return

    init_simulation_session()

    session_id = st.session_state["sim_session_id"]
    portfolio: Portfolio = st.session_state["sim_portfolio"]
    current_round: int = st.session_state["sim_current_round"]
    window: dict = st.session_state["sim_window"]
    stock_ids: list[str] = st.session_state["sim_stock_ids"]

    # -----------------------------------------------------------------------
    # Session complete state
    # -----------------------------------------------------------------------
    if st.session_state.get("sim_complete"):
        st.success("✅ Sesi Selesai! Menganalisis keputusan investasi kamu…")
        if st.button("Lihat Hasil Analisis →", use_container_width=True, type="primary"):
            st.session_state["last_session_id"] = session_id
            st.session_state["current_page"] = "Hasil Analisis & Umpan Balik"
            reset_simulation()
            st.rerun()
        return

    # -----------------------------------------------------------------------
    # Header — round counter + portfolio summary
    # -----------------------------------------------------------------------
    # Enhancement 2: Round progress bar
    st.progress(current_round / ROUNDS_PER_SESSION, text=f"Putaran {current_round} / {ROUNDS_PER_SESSION}")

    col_round, col_value, col_cash = st.columns(3)
    with col_round:
        st.metric("Putaran", f"{current_round} / {ROUNDS_PER_SESSION}")
    with col_value:
        # Compute current prices from this round's data
        round_data = {sid: window[sid][current_round - 1] for sid in stock_ids}
        current_prices = {sid: round_data[sid]["close"] for sid in stock_ids}
        total_value = portfolio.get_total_value(current_prices)
        delta = total_value - INITIAL_CAPITAL
        st.metric(
            "Nilai Portofolio",
            _format_rupiah(total_value),
            delta=_format_rupiah(delta),
            delta_color="normal",
        )
    with col_cash:
        st.metric("Kas Tersedia", _format_rupiah(portfolio.cash))

    # -----------------------------------------------------------------------
    # Holdings table
    # -----------------------------------------------------------------------
    if portfolio.holdings:
        st.markdown("**Posisi Terbuka:**")
        pnl_map = portfolio.get_pnl(current_prices)
        holding_rows = []
        for sid, pos in portfolio.holdings.items():
            curr = current_prices.get(sid, pos.avg_purchase_price)
            pnl = pnl_map.get(sid, 0.0)
            holding_rows.append({
                "Saham": sid,
                "Lembar": pos.quantity,
                "Harga Beli Rata-rata": _format_rupiah(pos.avg_purchase_price),
                "Harga Sekarang": _format_rupiah(curr),
                "P&L": f"{'+' if pnl >= 0 else ''}{_format_rupiah(pnl)}",
            })
        st.dataframe(holding_rows, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader(f"Data Pasar — Putaran {current_round}")

    # -----------------------------------------------------------------------
    # Per-stock cards + action controls
    # -----------------------------------------------------------------------
    action_inputs: dict[str, dict] = {}

    # Build price history per stock up to current round
    price_histories = {
        sid: [window[sid][i]["close"] for i in range(current_round)]
        for sid in stock_ids
    }

    cols = st.columns(2)
    for i, sid in enumerate(stock_ids):
        snap = round_data[sid]
        held_qty = portfolio.holdings.get(sid, None)

        with cols[i % 2]:
            with st.container(border=True):
                # Enhancement 1: Show full stock name and sector
                meta = st.session_state.get("stock_metadata", {}).get(sid, {})
                ticker = sid.split(".")[0]
                name_str = meta.get("name", "")
                sector_str = meta.get("sector", "")
                if name_str:
                    st.markdown(f"**{ticker}** — {name_str} *({sector_str})*")
                else:
                    st.markdown(f"**{sid}**")
                trend = snap.get("trend") or "—"
                daily_ret = snap.get("daily_return")
                ret_str = f"{daily_ret*100:+.2f}%" if daily_ret is not None else "—"
                st.metric(
                    label=f"Harga Penutupan",
                    value=_format_rupiah(snap["close"]),
                    delta=ret_str,
                )

                # Technical indicator row
                ma5 = snap.get("ma_5")
                ma20 = snap.get("ma_20")
                ind_cols = st.columns(3)
                ind_cols[0].caption(f"MA5: {_format_rupiah(ma5) if ma5 else '—'}")
                ind_cols[1].caption(f"MA20: {_format_rupiah(ma20) if ma20 else '—'}")
                ind_cols[2].caption(f"Tren: {trend.capitalize()}")

                # Price chart with MA overlays
                ma5_hist = [
                    window[sid][i]["ma_5"]
                    for i in range(current_round)
                    if window[sid][i].get("ma_5") is not None
                ]
                ma20_hist = [
                    window[sid][i]["ma_20"]
                    for i in range(current_round)
                    if window[sid][i].get("ma_20") is not None
                ]
                fig = _build_price_chart(sid, price_histories[sid], current_round, ma5_hist or None, ma20_hist or None)
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{sid}_{current_round}")

                # Action controls
                action_type = st.radio(
                    "Keputusan",
                    options=["Tahan", "Beli", "Jual"],
                    key=f"action_{sid}",
                    horizontal=True,
                )

                quantity = 0
                if action_type in ("Beli", "Jual"):
                    max_buy = int(portfolio.cash // snap["close"]) if snap["close"] > 0 else 0
                    max_sell = held_qty.quantity if held_qty else 0

                    if action_type == "Beli":
                        quantity = st.number_input(
                            "Jumlah lembar (Beli)",
                            min_value=0, max_value=max(max_buy, 0),
                            value=0, step=1,
                            key=f"qty_buy_{sid}",
                        )
                    else:
                        quantity = st.number_input(
                            "Jumlah lembar (Jual)",
                            min_value=0, max_value=max(max_sell, 0),
                            value=0, step=1,
                            key=f"qty_sell_{sid}",
                        )

                action_inputs[sid] = {
                    "action_type": action_type,
                    "quantity": quantity,
                    "snap": snap,
                }

    # -----------------------------------------------------------------------
    # Submit button
    # -----------------------------------------------------------------------
    st.markdown("---")
    # Enhancement 5: Round submission guard — prevent double-submission
    if st.session_state.get("sim_submitted_round") == current_round:
        st.info("Putaran ini sudah dieksekusi. Menunggu putaran berikutnya…")
        return

    if st.button("✅ Eksekusi Keputusan", use_container_width=True, type="primary"):
        response_time_ms = int((time.time() - st.session_state["sim_round_start_time"]) * 1000)

        errors = []
        with get_session() as sess:
            for sid, inp in action_inputs.items():
                atype = inp["action_type"]
                qty = inp["quantity"]
                snap = inp["snap"]
                price = snap["close"]

                # Map Bahasa → internal
                atype_en = {"Beli": "buy", "Jual": "sell", "Tahan": "hold"}[atype]

                # Attempt portfolio update
                try:
                    if atype_en == "buy" and qty > 0:
                        portfolio.buy(sid, qty, price, current_round)
                    elif atype_en == "sell" and qty > 0:
                        portfolio.sell(sid, qty, price, current_round)
                except ValueError as e:
                    errors.append(str(e))
                    atype_en = "hold"
                    qty = 0

                actual_value = qty * price if qty > 0 else 0.0

                log_action(
                    session=sess,
                    user_id=user_id,
                    session_id=session_id,
                    scenario_round=current_round,
                    stock_id=sid,
                    snapshot_id=snap["id"],
                    action_type=atype_en,
                    quantity=qty,
                    action_value=actual_value,
                    response_time_ms=response_time_ms,
                )

        if errors:
            for err in errors:
                st.error(err)

        # Mark this round as submitted (Enhancement 5 + Bug 9 guard)
        st.session_state["sim_submitted_round"] = current_round

        # Advance round
        next_round = current_round + 1
        st.session_state["sim_current_round"] = next_round
        st.session_state["sim_round_start_time"] = time.time()

        # Bug 9 fix: set sim_complete BEFORE running the pipeline to prevent
        # duplicate execution if st.rerun() fires before the state is committed
        if next_round > ROUNDS_PER_SESSION and not st.session_state.get("sim_complete"):
            st.session_state["sim_complete"] = True
            with st.spinner("Menganalisis keputusan investasi kamu…"):
                _run_post_session_pipeline(user_id, session_id)

        st.rerun()
