"""
modules/simulation/ui.py — Streamlit simulation UI page.

Renders the 14-round investment simulation with a trading-platform layout:
- Left sidebar: stock selector + open positions summary
- Right panel: candlestick chart with pre-window history, order form
- Pending orders accumulate per round; single "Eksekusi Semua" button commits all

Logs all user actions (buy/sell/hold) and triggers the full analytics +
CDT + feedback pipeline after round 14.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from config import INITIAL_CAPITAL, ROUNDS_PER_SESSION
from database.connection import get_session
from database.models import StockCatalog
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


def _build_full_chart(
    stock_id: str,
    pre_history: list[dict],
    window_data: list[dict],
    current_round: int,
) -> go.Figure:
    """Build a candlestick chart showing pre-window history + trading window.

    Args:
        stock_id:     Stock identifier (used for chart title).
        pre_history:  Dicts with keys date/open/high/low/close/ma_5/ma_20.
                      Shown dimmed before the trading window starts.
        window_data:  Full 14-day window dicts from sim_window[sid].
        current_round: How many rounds of the window to show (1-indexed).
    """
    fig = go.Figure()

    # --- Pre-window history (dimmed line) ---
    if pre_history:
        pre_dates = [
            d["date"].isoformat() if hasattr(d["date"], "isoformat") else str(d["date"])
            for d in pre_history
        ]
        pre_closes = [d["close"] for d in pre_history]
        fig.add_trace(go.Scatter(
            x=pre_dates, y=pre_closes,
            mode="lines", name="Riwayat",
            line=dict(color="rgba(150,150,150,0.5)", width=1),
            hovertemplate="%{x}<br>Harga: %{y:,.0f}<extra></extra>",
        ))

        # Pre-window MA overlays (dimmed)
        pre_ma5 = [d.get("ma_5") for d in pre_history]
        pre_ma20 = [d.get("ma_20") for d in pre_history]
        if any(v is not None for v in pre_ma5):
            fig.add_trace(go.Scatter(
                x=pre_dates, y=pre_ma5,
                mode="lines", name="MA5 (historis)",
                line=dict(color="rgba(255,127,14,0.3)", width=1, dash="dash"),
                hoverinfo="skip",
            ))
        if any(v is not None for v in pre_ma20):
            fig.add_trace(go.Scatter(
                x=pre_dates, y=pre_ma20,
                mode="lines", name="MA20 (historis)",
                line=dict(color="rgba(44,160,44,0.3)", width=1, dash="dot"),
                hoverinfo="skip",
            ))

    # --- Trading window up to current_round (candlestick) ---
    visible = window_data[:current_round]
    if visible:
        win_dates = [
            d["date"].isoformat() if hasattr(d["date"], "isoformat") else str(d["date"])
            for d in visible
        ]
        fig.add_trace(go.Candlestick(
            x=win_dates,
            open=[d["open"] for d in visible],
            high=[d["high"] for d in visible],
            low=[d["low"] for d in visible],
            close=[d["close"] for d in visible],
            name="Harga",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ))

        # MA overlays for trading window
        ma5_vals = [d.get("ma_5") for d in visible]
        ma20_vals = [d.get("ma_20") for d in visible]
        if any(v is not None for v in ma5_vals):
            fig.add_trace(go.Scatter(
                x=win_dates, y=ma5_vals,
                mode="lines", name="MA5",
                line=dict(color="#ff7f0e", width=1.5, dash="dash"),
                hovertemplate="MA5: %{y:,.0f}<extra></extra>",
            ))
        if any(v is not None for v in ma20_vals):
            fig.add_trace(go.Scatter(
                x=win_dates, y=ma20_vals,
                mode="lines", name="MA20",
                line=dict(color="#2ca02c", width=1.5, dash="dot"),
                hovertemplate="MA20: %{y:,.0f}<extra></extra>",
            ))

        # Vertical marker at window start
        fig.add_vline(
            x=win_dates[0],
            line_dash="dash",
            line_color="rgba(0,0,255,0.5)",
            annotation_text="Mulai Trading",
            annotation_position="top right",
            annotation_font_size=10,
        )

    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=-0.15, font=dict(size=10)),
        xaxis_title=None,
        yaxis_title="Harga (Rp)",
        plot_bgcolor="white",
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
            # Serialize window data (snapshots) to plain dicts
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
            # Fetch pre-window history while session is still active
            pre_history = engine.get_pre_window_history()
            st.session_state["sim_pre_history"] = pre_history
        st.session_state["sim_engine"] = True  # prevents re-init on every rerun

    if "sim_current_round" not in st.session_state:
        st.session_state["sim_current_round"] = 1

    if "sim_round_start_time" not in st.session_state:
        st.session_state["sim_round_start_time"] = time.time()

    if "sim_complete" not in st.session_state:
        st.session_state["sim_complete"] = False

    if "sim_submitted_round" not in st.session_state:
        st.session_state["sim_submitted_round"] = 0

    if "sim_pending_orders" not in st.session_state:
        st.session_state["sim_pending_orders"] = {}

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
        "sim_submitted_round", "stock_metadata", "sim_pre_history", "sim_pending_orders",
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
# Round execution helper
# ---------------------------------------------------------------------------

def _execute_round(
    user_id: int,
    session_id: str,
    portfolio: Portfolio,
    current_round: int,
    window: dict,
    stock_ids: list[str],
    pending_orders: dict,
) -> None:
    """Process all pending orders and auto-log 'hold' for non-traded stocks.

    Advances the round counter and triggers the post-session pipeline if
    round 14 is complete, then calls st.rerun().
    """
    response_time_ms = int(
        (time.time() - st.session_state["sim_round_start_time"]) * 1000
    )

    errors: list[str] = []
    with get_session() as sess:
        for sid in stock_ids:
            snap = window[sid][current_round - 1]
            price = snap["close"]

            if sid in pending_orders:
                order = pending_orders[sid]
                atype_bahasa = order["action_type"]
                qty = order["quantity"]
                atype_en = {"Beli": "buy", "Jual": "sell"}.get(atype_bahasa, "hold")

                try:
                    if atype_en == "buy" and qty > 0:
                        portfolio.buy(sid, qty, price, current_round)
                    elif atype_en == "sell" and qty > 0:
                        portfolio.sell(sid, qty, price, current_round)
                    else:
                        atype_en = "hold"
                        qty = 0
                except ValueError as e:
                    errors.append(str(e))
                    atype_en = "hold"
                    qty = 0
            else:
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

    # Advance round
    next_round = current_round + 1
    st.session_state["sim_current_round"] = next_round
    st.session_state["sim_round_start_time"] = time.time()
    st.session_state["sim_pending_orders"] = {}

    if next_round > ROUNDS_PER_SESSION and not st.session_state.get("sim_complete"):
        st.session_state["sim_complete"] = True
        with st.spinner("Menganalisis keputusan investasi kamu…"):
            _run_post_session_pipeline(user_id, session_id)

    st.rerun()


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
    pre_history_all: dict = st.session_state.get("sim_pre_history", {})
    pending: dict = st.session_state.get("sim_pending_orders", {})

    # -----------------------------------------------------------------------
    # Session complete state
    # -----------------------------------------------------------------------
    if st.session_state.get("sim_complete"):
        st.success("Sesi Selesai! Menganalisis keputusan investasi kamu…")
        if st.button("Lihat Hasil Analisis →", use_container_width=True, type="primary"):
            st.session_state["last_session_id"] = session_id
            st.session_state["current_page"] = "Hasil Analisis & Umpan Balik"
            reset_simulation()
            st.rerun()
        return

    # -----------------------------------------------------------------------
    # Top bar: progress + portfolio summary
    # -----------------------------------------------------------------------
    st.progress(
        current_round / ROUNDS_PER_SESSION,
        text=f"Putaran {current_round} / {ROUNDS_PER_SESSION}",
    )

    round_data = {sid: window[sid][current_round - 1] for sid in stock_ids}
    current_prices = {sid: round_data[sid]["close"] for sid in stock_ids}
    total_value = portfolio.get_total_value(current_prices)
    delta = total_value - INITIAL_CAPITAL
    realized_pnl = portfolio.get_realized_pnl()

    c_val, c_cash, c_pnl = st.columns(3)
    c_val.metric(
        "Nilai Portofolio",
        _format_rupiah(total_value),
        delta=_format_rupiah(delta),
        delta_color="normal",
    )
    c_cash.metric("Kas Tersedia", _format_rupiah(portfolio.cash))
    c_pnl.metric(
        "Realized P&L",
        _format_rupiah(realized_pnl),
        delta_color="normal",
    )

    # Guide expander
    with st.expander("Panduan Simulasi", expanded=False):
        st.markdown("""
**Cara bermain:**
- Setiap putaran mewakili **1 hari trading** menggunakan data historis saham IDX
- Pilih saham dari daftar di sebelah kiri, lalu lihat grafik harga dan indikator teknikal
- Tentukan keputusan: **Beli**, **Jual**, atau **Tahan** (default: Tahan)
- Klik **Konfirmasi** untuk menyimpan keputusan, lalu klik **Eksekusi Semua** untuk mengonfirmasi semua keputusan dan lanjut ke putaran berikutnya

**Membaca grafik:**
- **Candlestick hijau** = harga naik, **merah** = harga turun
- Area abu-abu di kiri = riwayat sebelum simulasi dimulai
- **MA5** (garis putus oranye) = rata-rata 5 hari
- **MA20** (garis titik hijau) = rata-rata 20 hari

**Tips:** Tidak perlu trading setiap saham setiap putaran. Saham yang tidak dikonfirmasi akan otomatis dicatat sebagai **Tahan**.
        """)

    st.divider()

    # -----------------------------------------------------------------------
    # Main layout: left (stock list + holdings) | right (chart + order panel)
    # -----------------------------------------------------------------------
    col_left, col_right = st.columns([1, 3])

    with col_left:
        st.markdown("**Pilih Saham**")
        meta_map = st.session_state.get("stock_metadata", {})

        selected_stock = st.radio(
            "Saham",
            options=stock_ids,
            format_func=lambda sid: (
                f"{sid.split('.')[0]} — {meta_map.get(sid, {}).get('name', '')}"
            ),
            key="selected_stock",
            label_visibility="collapsed",
        )

        st.divider()
        st.markdown("**Posisi Terbuka**")
        if portfolio.holdings:
            for sid, pos in portfolio.holdings.items():
                curr = current_prices.get(sid, pos.avg_purchase_price)
                pnl = (curr - pos.avg_purchase_price) * pos.quantity
                icon = "🟢" if pnl >= 0 else "🔴"
                st.caption(
                    f"{icon} **{sid.split('.')[0]}**: {pos.quantity} lbr "
                    f"@ {_format_rupiah(pos.avg_purchase_price)}"
                )
        else:
            st.caption("Belum ada posisi terbuka")

        # Show pending orders in sidebar
        if pending:
            st.divider()
            st.markdown("**Keputusan Putaran Ini:**")
            for sid, order in pending.items():
                ticker = sid.split(".")[0]
                st.caption(
                    f"**{ticker}**: {order['action_type']} {order['quantity']} lbr"
                )

    with col_right:
        sid = selected_stock
        snap = round_data[sid]
        pre_hist = pre_history_all.get(sid, [])
        win_data = window[sid]
        meta = meta_map.get(sid, {})
        ticker = sid.split(".")[0]

        # Stock header
        st.markdown(
            f"**{ticker}** — {meta.get('name', '')} "
            f"*({meta.get('sector', '')})*"
        )

        # Candlestick chart
        fig = _build_full_chart(sid, pre_hist, win_data, current_round)
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{sid}_{current_round}")

        # Technical indicators row
        ma5 = snap.get("ma_5")
        ma20 = snap.get("ma_20")
        trend = snap.get("trend") or "—"
        rsi = snap.get("rsi_14")
        daily_ret = snap.get("daily_return")
        ret_str = f"{daily_ret * 100:+.2f}%" if daily_ret is not None else "—"

        ind_cols = st.columns(4)
        ind_cols[0].metric("Harga", _format_rupiah(snap["close"]), delta=ret_str)
        ind_cols[1].caption(f"MA5: {_format_rupiah(ma5) if ma5 else '—'}")
        ind_cols[2].caption(f"MA20: {_format_rupiah(ma20) if ma20 else '—'}")
        rsi_str = f"{rsi:.0f}" if rsi is not None else "—"
        ind_cols[3].caption(f"Tren: {trend.capitalize()} | RSI: {rsi_str}")

        st.divider()

        # Order panel inside a form (prevents rerun on every widget change)
        with st.form(f"order_{current_round}_{sid}", clear_on_submit=False):
            st.markdown(f"**Keputusan untuk {ticker}**")
            held = portfolio.holdings.get(sid)

            # Pre-fill from pending if already confirmed
            existing_order = pending.get(sid, {})
            default_action_idx = 0
            action_options = ["Tahan", "Beli", "Jual"]
            if existing_order.get("action_type") in action_options:
                default_action_idx = action_options.index(existing_order["action_type"])

            action_type = st.radio(
                "Aksi",
                action_options,
                index=default_action_idx,
                horizontal=True,
                key=f"action_form_{sid}_{current_round}",
            )

            quantity = 0
            if action_type == "Beli":
                max_buy = int(portfolio.cash // snap["close"]) if snap["close"] > 0 else 0
                default_qty = existing_order.get("quantity", 0) if existing_order.get("action_type") == "Beli" else 0
                quantity = st.number_input(
                    "Jumlah lembar",
                    min_value=0,
                    max_value=max(max_buy, 0),
                    value=min(default_qty, max_buy),
                    step=1,
                    key=f"qty_buy_form_{sid}_{current_round}",
                )
                if quantity > 0:
                    st.caption(f"Estimasi biaya: {_format_rupiah(quantity * snap['close'])}")
            elif action_type == "Jual":
                max_sell = held.quantity if held else 0
                default_qty = existing_order.get("quantity", 0) if existing_order.get("action_type") == "Jual" else 0
                quantity = st.number_input(
                    "Jumlah lembar",
                    min_value=0,
                    max_value=max(max_sell, 0),
                    value=min(default_qty, max_sell),
                    step=1,
                    key=f"qty_sell_form_{sid}_{current_round}",
                )
                if quantity > 0 and held:
                    pnl_est = (snap["close"] - held.avg_purchase_price) * quantity
                    pnl_sign = "+" if pnl_est >= 0 else ""
                    st.caption(f"Estimasi P&L: {pnl_sign}{_format_rupiah(pnl_est)}")

            order_submitted = st.form_submit_button(
                f"Konfirmasi {action_type} {ticker}",
                use_container_width=True,
            )

        if order_submitted:
            if action_type != "Tahan" and quantity > 0:
                pending[sid] = {"action_type": action_type, "quantity": quantity}
            elif sid in pending:
                # User switched back to Tahan — remove pending order
                del pending[sid]
            st.session_state["sim_pending_orders"] = pending
            st.rerun()

    # -----------------------------------------------------------------------
    # Execute round button (outside columns, outside form)
    # -----------------------------------------------------------------------
    st.divider()

    # Guard against double-submission
    if st.session_state.get("sim_submitted_round") == current_round:
        st.info("Putaran ini sudah dieksekusi. Menunggu putaran berikutnya…")
        return

    execute_label = (
        f"Eksekusi Semua & Lanjut ke Putaran {current_round + 1}"
        if current_round < ROUNDS_PER_SESSION
        else "Selesaikan Sesi (Putaran Terakhir)"
    )
    if st.button(f"✅ {execute_label}", use_container_width=True, type="primary"):
        st.session_state["sim_submitted_round"] = current_round
        _execute_round(
            user_id, session_id, portfolio,
            current_round, window, stock_ids, pending,
        )
