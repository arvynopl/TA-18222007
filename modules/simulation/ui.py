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
from plotly.subplots import make_subplots

from config import INITIAL_CAPITAL, ROUNDS_PER_SESSION
from modules.utils.layout import is_mobile, responsive_columns
from modules.utils.ui_helpers import apply_chart_theme, CHART_TEXT, COLOR_GAIN, COLOR_LOSS, render_coach_mark_onboarding
from database.connection import get_session
from database.models import StockCatalog
from modules.analytics.bias_metrics import compute_and_save_metrics
from modules.analytics.features import extract_session_features
from modules.cdt.updater import update_profile
from modules.feedback.generator import generate_feedback
from modules.logging_engine.logger import log_action
from modules.logging_engine.validator import validate_session_completeness
from modules.simulation.engine import SimulationEngine
from modules.simulation.portfolio import Portfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_rupiah(value: float) -> str:
    """Format a float as Indonesian Rupiah string."""
    return f"Rp {value:,.0f}"


ACTION_LABELS = {"buy": "Beli", "sell": "Jual", "hold": "Tahan"}

# Bahasa → internal action key
_ACTION_ID_FROM_BAHASA = {"Beli": "buy", "Jual": "sell", "Tahan": "hold"}


def build_order_button_label(action_type: str, ticker: str) -> str:
    """Produce the reactive confirm-button label for the order panel.

    Accepts either the Bahasa label (``Beli/Jual/Tahan``) or the internal
    action id (``buy/sell/hold``). ``Tahan`` / ``hold`` renders a
    "Konfirmasi: …" label since no queue change is needed, while the other
    two render "Tambahkan ke Antrean: …".
    """
    ticker = ticker or ""
    action_id = _ACTION_ID_FROM_BAHASA.get(action_type, action_type)
    bahasa = ACTION_LABELS.get(action_id, action_type)
    if action_id == "hold":
        return f"Konfirmasi: {bahasa} {ticker}".rstrip()
    return f"Tambahkan ke Antrean: {bahasa} {ticker}".rstrip()


def compute_projected_end_round_cash(
    portfolio, current_prices: dict
) -> float:
    """Hypothetical cash if every open position is liquidated at current prices.

    Formula: ``cash + Σ (qty × price)`` across all holdings.
    Stocks absent from ``current_prices`` fall back to their average purchase
    price so the projection stays defined even with missing snapshots.
    """
    total = float(portfolio.cash)
    for sid, pos in portfolio.holdings.items():
        px = current_prices.get(sid, pos.avg_purchase_price)
        total += float(pos.quantity) * float(px)
    return total


def _build_compact_line_chart(
    stock_id: str,
    pre_history: list[dict],
    window_data: list[dict],
    current_round: int,
) -> go.Figure:
    """Mobile-friendly closing-price line chart.

    Drops the candlestick + volume subplot in favour of a single line
    that preserves the bias-relevant information: price trajectory and
    where the trading window starts. Used when the user enables
    'Tampilan ringkas untuk mobile' (or when Mode mobile is on).
    """
    fig = go.Figure()

    if pre_history:
        pre_dates = [
            d["date"].isoformat() if hasattr(d["date"], "isoformat") else str(d["date"])
            for d in pre_history
        ]
        fig.add_trace(go.Scatter(
            x=pre_dates,
            y=[d["close"] for d in pre_history],
            mode="lines",
            name="Riwayat",
            line=dict(color="rgba(95,99,104,0.55)", width=1.5),
            hovertemplate="Tutup: %{y:,.0f}<extra></extra>",
        ))

    visible = window_data[: current_round]
    if visible:
        win_dates = [
            d["date"].isoformat() if hasattr(d["date"], "isoformat") else str(d["date"])
            for d in visible
        ]
        win_closes = [d["close"] for d in visible]
        gain = win_closes[-1] >= win_closes[0]
        fig.add_trace(go.Scatter(
            x=win_dates,
            y=win_closes,
            mode="lines+markers",
            name="Harga",
            line=dict(color=(COLOR_GAIN if gain else COLOR_LOSS), width=2),
            marker=dict(size=4),
            hovertemplate="Tutup: %{y:,.0f}<extra></extra>",
        ))

        if current_round > 1:
            fig.add_shape(
                type="line",
                x0=win_dates[0], x1=win_dates[0],
                y0=0, y1=1,
                yref="paper",
                line=dict(dash="dash", color="rgba(74,144,226,0.6)"),
            )
            fig.add_annotation(
                x=win_dates[0],
                y=1,
                yref="paper",
                text="Mulai Trading",
                showarrow=False,
                font=dict(size=10, color=CHART_TEXT),
                xanchor="left",
            )

    apply_chart_theme(fig, height=280)
    fig.update_layout(
        legend=dict(
            x=0,
            y=1.18,
            orientation="h",
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
        ),
        margin=dict(l=8, r=8, t=24, b=8),
    )
    fig.update_xaxes(type="category", gridcolor="rgba(0,0,0,0.08)")
    fig.update_yaxes(title_text="Harga (Rp)", gridcolor="rgba(0,0,0,0.08)")
    return fig


def _build_full_chart(
    stock_id: str,
    pre_history: list[dict],
    window_data: list[dict],
    current_round: int,
    compact: bool = False,
) -> go.Figure:
    """Build a candlestick + volume chart showing pre-window history + trading window.

    Args:
        stock_id:     Stock identifier (used for chart title).
        pre_history:  Dicts with keys date/open/high/low/close/volume/ma_5/ma_20.
                      Shown dimmed before the trading window starts.
        window_data:  Full 14-day window dicts from sim_window[sid].
        current_round: How many rounds of the window to show (1-indexed).
        compact:      When True, render a simplified single-line price chart
                      sized for narrow viewports (mobile). Bias-relevant
                      information (trajectory, trading window boundary) is
                      preserved; volume + MA overlays are dropped.
    """
    if compact:
        return _build_compact_line_chart(stock_id, pre_history, window_data, current_round)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.02,
    )

    # --- Pre-window history (muted candlesticks + MA overlays) ---
    if pre_history:
        pre_dates = [
            d["date"].isoformat() if hasattr(d["date"], "isoformat") else str(d["date"])
            for d in pre_history
        ]
        fig.add_trace(go.Candlestick(
            x=pre_dates,
            open=[d["open"] for d in pre_history],
            high=[d["high"] for d in pre_history],
            low=[d["low"] for d in pre_history],
            close=[d["close"] for d in pre_history],
            name="Riwayat",
            increasing=dict(
                line=dict(color=COLOR_GAIN),
                fillcolor=COLOR_GAIN,
            ),
            decreasing=dict(
                line=dict(color=COLOR_LOSS),
                fillcolor=COLOR_LOSS,
            ),
            opacity=0.45,  # muted historical window
            showlegend=True,
        ), row=1, col=1)

        # Pre-window MA overlays (dimmed)
        pre_ma5 = [d.get("ma_5") for d in pre_history]
        pre_ma20 = [d.get("ma_20") for d in pre_history]
        if any(v is not None for v in pre_ma5):
            fig.add_trace(go.Scatter(
                x=pre_dates, y=pre_ma5,
                mode="lines", name="MA5 (historis)",
                line=dict(color="rgba(227,116,0,0.35)", width=1, dash="dash"),
                hoverinfo="skip",
            ), row=1, col=1)
        if any(v is not None for v in pre_ma20):
            fig.add_trace(go.Scatter(
                x=pre_dates, y=pre_ma20,
                mode="lines", name="MA20 (historis)",
                line=dict(color="rgba(44,160,44,0.3)", width=1, dash="dot"),
                hoverinfo="skip",
            ), row=1, col=1)

        # Pre-window volume bars — colour-matched to OHLC direction at 0.45 opacity.
        pre_vols = [d.get("volume") or 0 for d in pre_history]
        pre_vol_colors = [
            f"rgba({int(COLOR_GAIN[1:3],16)},{int(COLOR_GAIN[3:5],16)},{int(COLOR_GAIN[5:],16)},0.45)"
            if d["close"] >= d["open"]
            else f"rgba({int(COLOR_LOSS[1:3],16)},{int(COLOR_LOSS[3:5],16)},{int(COLOR_LOSS[5:],16)},0.45)"
            for d in pre_history
        ]
        fig.add_trace(go.Bar(
            x=pre_dates, y=pre_vols,
            name="Volume (historis)",
            marker_color=pre_vol_colors,
            showlegend=False,
            hoverinfo="skip",
        ), row=2, col=1)

    # --- Trading window up to current_round (candlestick) ---
    display_count = current_round
    visible = window_data[:display_count]
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
            increasing_line_color=COLOR_GAIN,
            decreasing_line_color=COLOR_LOSS,
        ), row=1, col=1)

        # Plotly single-candle workaround: invisible scatter anchor prevents x-axis collapse
        if display_count == 1 and visible:
            fig.add_trace(go.Scatter(
                x=[win_dates[0]],
                y=[visible[0]["close"]],
                mode="markers",
                marker=dict(size=0, opacity=0, color="rgba(0,0,0,0)"),
                showlegend=False,
                hoverinfo="skip",
                name="_anchor",
            ), row=1, col=1)

        # MA overlays for trading window
        ma5_vals = [d.get("ma_5") for d in visible]
        ma20_vals = [d.get("ma_20") for d in visible]
        if any(v is not None for v in ma5_vals):
            fig.add_trace(go.Scatter(
                x=win_dates, y=ma5_vals,
                mode="lines", name="MA5",
                line=dict(color="#ff7f0e", width=1.5, dash="dash"),
                hovertemplate="MA5: %{y:,.0f}<extra></extra>",
            ), row=1, col=1)
        if any(v is not None for v in ma20_vals):
            fig.add_trace(go.Scatter(
                x=win_dates, y=ma20_vals,
                mode="lines", name="MA20",
                line=dict(color="#2ca02c", width=1.5, dash="dot"),
                hovertemplate="MA20: %{y:,.0f}<extra></extra>",
            ), row=1, col=1)

        # Volume bars for trading window
        win_vols = [d.get("volume") or 0 for d in visible]
        win_vol_colors = [
            COLOR_GAIN if d["close"] >= d["open"] else COLOR_LOSS
            for d in visible
        ]
        fig.add_trace(go.Bar(
            x=win_dates, y=win_vols,
            name="Volume",
            marker_color=win_vol_colors,
            showlegend=False,
            hovertemplate="Vol: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)

        # Vertical marker at window start (add_vline with annotation_text
        # fails on date strings due to a Plotly internal mean() call, so
        # use add_shape + add_annotation separately).
        # Suppress on round 1: only 1 real bar exists so the boundary marker
        # is meaningless and visually confusing.
        if current_round > 1:
            fig.add_shape(
                type="line",
                x0=win_dates[0], x1=win_dates[0],
                y0=0, y1=1,
                yref="paper",
                line=dict(dash="dash", color="rgba(74,144,226,0.6)"),
            )
            fig.add_annotation(
                x=win_dates[0],
                y=1,
                yref="paper",
                text="Mulai Trading",
                showarrow=False,
                font=dict(size=10, color=CHART_TEXT),
                xanchor="left",
            )

    apply_chart_theme(fig, height=420)
    fig.update_layout(
        legend=dict(
            x=0,
            y=1.18,
            orientation="h",
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
        )
    )
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(title_text="Harga (Rp)", row=1, col=1, gridcolor="rgba(0,0,0,0.08)")
    fig.update_yaxes(title_text="Volume", row=2, col=1, gridcolor="rgba(0,0,0,0.08)")
    fig.update_xaxes(type="category", gridcolor="rgba(0,0,0,0.08)")
    return fig


# ---------------------------------------------------------------------------
# Session initialisation
# ---------------------------------------------------------------------------

def init_simulation_session() -> None:
    """Initialise Streamlit session state for a new simulation session."""
    if "sim_session_id" not in st.session_state:
        st.session_state["sim_session_id"] = str(uuid.uuid4())
        # Persist session start
        from database.models import SessionSummary
        from datetime import datetime, timezone
        user_id = st.session_state.get("user_id")
        if user_id:
            with get_session() as sess:
                sess.add(SessionSummary(
                    user_id=user_id,
                    session_id=st.session_state["sim_session_id"],
                    started_at=datetime.now(timezone.utc),
                    status="in_progress",
                ))

    if "sim_portfolio" not in st.session_state:
        st.session_state["sim_portfolio"] = Portfolio(INITIAL_CAPITAL)

    if "sim_engine" not in st.session_state:
        user_id = st.session_state.get("user_id")
        session_id = st.session_state["sim_session_id"]
        try:
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
                # Store window date range for SessionSummary
                if engine.stock_ids:
                    first_stock = engine.stock_ids[0]
                    st.session_state["sim_window_start"] = engine._window[first_stock][0].date
                    st.session_state["sim_window_end"] = engine._window[first_stock][-1].date
                # Fetch pre-window history while session is still active
                pre_history = engine.get_pre_window_history()
                st.session_state["sim_pre_history"] = pre_history
            st.session_state["sim_engine"] = True  # prevents re-init on every rerun
        except Exception:
            # Engine failed to initialise — mark the orphaned SessionSummary as
            # abandoned so it doesn't stay "in_progress" forever.
            from database.models import SessionSummary
            from datetime import datetime, timezone
            _pipeline_logger.exception(
                "user=%s session=%s engine init failed; marking session abandoned",
                user_id, session_id,
            )
            try:
                with get_session() as err_sess:
                    summary = err_sess.query(SessionSummary).filter_by(session_id=session_id).first()
                    if summary:
                        summary.status = "abandoned"
                        summary.completed_at = datetime.now(timezone.utc)
            except Exception:
                pass
            # Clear the session_id so a new one will be created on retry
            st.session_state.pop("sim_session_id", None)
            st.error(
                "Tidak dapat memuat data pasar untuk sesi ini. "
                "Pastikan database sudah di-seed (`python -m database.seed`) lalu muat ulang halaman."
            )
            return

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

    if "stock_descriptions" not in st.session_state:
        try:
            import json
            from config import STOCK_CATALOG_FILE
            with open(STOCK_CATALOG_FILE, "r", encoding="utf-8") as _f:
                _catalog = json.load(_f)
            st.session_state["stock_descriptions"] = {
                item["stock_id"]: {
                    "description": item.get("description", ""),
                    "volatility_class": item.get("volatility_class", ""),
                }
                for item in _catalog
            }
        except Exception:
            st.session_state["stock_descriptions"] = {}


def reset_simulation() -> None:
    """Clear all simulation-related state keys to start fresh."""
    for key in [
        "sim_session_id", "sim_portfolio", "sim_engine", "sim_window",
        "sim_stock_ids", "sim_current_round", "sim_round_start_time", "sim_complete",
        "sim_submitted_round", "stock_metadata", "sim_pre_history", "sim_pending_orders",
        "stock_descriptions",
    ]:
        st.session_state.pop(key, None)


# ---------------------------------------------------------------------------
# Post-session pipeline
# ---------------------------------------------------------------------------

import logging as _logging
_pipeline_logger = _logging.getLogger(__name__)


def _run_post_session_pipeline(user_id: int, session_id: str) -> None:
    """Trigger analytics → CDT update → feedback generation after session ends.

    On any failure, marks the session as "error" and re-raises so the caller
    can show a user-facing message. This ensures SessionSummary never stays
    "in_progress" after the pipeline exits.
    """
    from database.models import SessionSummary
    from datetime import datetime, timezone

    try:
        with get_session() as sess:
            # 0. Validate session completeness — warn if any rounds are missing
            completeness = validate_session_completeness(sess, user_id, session_id)
            if not completeness["is_complete"]:
                _pipeline_logger.warning(
                    "user=%s session=%s incomplete: %d/%d actions logged, "
                    "missing rounds=%s",
                    user_id, session_id,
                    completeness["action_count"], completeness["expected_count"],
                    completeness["missing_rounds"],
                )

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

            # 5. Update session summary — only reached if all steps above succeed
            summary = sess.query(SessionSummary).filter_by(session_id=session_id).first()
            if summary:
                summary.status = "completed"
                summary.completed_at = datetime.now(timezone.utc)
                summary.rounds_completed = ROUNDS_PER_SESSION
                summary.final_portfolio_value = features.final_value
                summary.window_start_date = st.session_state.get("sim_window_start")
                summary.window_end_date = st.session_state.get("sim_window_end")

    except Exception:
        _pipeline_logger.exception(
            "user=%s session=%s post-session pipeline failed; marking session as error",
            user_id, session_id,
        )
        # Mark session as error so it doesn't stay stuck as "in_progress"
        try:
            with get_session() as err_sess:
                summary = err_sess.query(SessionSummary).filter_by(session_id=session_id).first()
                if summary and summary.status != "completed":
                    summary.status = "error"
                    summary.completed_at = datetime.now(timezone.utc)
        except Exception:
            _pipeline_logger.exception(
                "user=%s session=%s failed to update session status to error",
                user_id, session_id,
            )
        raise


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
            try:
                _run_post_session_pipeline(user_id, session_id)
                # Pipeline succeeded — auto-redirect to results page.
                st.session_state["last_session_id"] = session_id
                st.session_state["current_page"] = "Hasil Analisis & Umpan Balik"
                reset_simulation()
                st.rerun()
            except Exception:
                st.error(
                    "Terjadi kesalahan saat menganalisis sesi. "
                    "Silakan hubungi administrator dengan kode sesi: "
                    f"{session_id[:8]}"
                )

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

    # Coach-mark onboarding — shown exactly once before the first simulation
    if not render_coach_mark_onboarding():
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
        st.markdown("## 🎯 Sesi Selesai!")
        st.markdown("Semua 14 putaran telah diselesaikan. Sistem sedang menganalisis pola keputusanmu…")

        final_prices = {sid: window[sid][-1]["close"] for sid in stock_ids}
        final_value = portfolio.get_total_value(final_prices)
        return_pct = ((final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100

        c1, c2, c3 = responsive_columns(3)
        c1.metric("Nilai Akhir", _format_rupiah(final_value))
        c2.metric("Return", f"{return_pct:+.1f}%")
        c3.metric("Total Transaksi", f"{len(portfolio.get_sold_trades())} trades")

        st.divider()
        if st.button("📊 Lihat Hasil Analisis →", use_container_width=True, type="primary"):
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

    # BALANCE-01: compute net impact of all queued orders this round.
    # available_cash (for max_buy validation) still deducts pending buys only.
    pending_buy_cost = sum(
        order["quantity"] * round_data[sid]["close"]
        for sid, order in pending.items()
        if order.get("action_type") == "Beli" and sid in round_data
    )
    pending_sell_proceeds = sum(
        order["quantity"] * round_data[sid]["close"]
        for sid, order in pending.items()
        if order.get("action_type") == "Jual" and sid in round_data
    )
    net_pending = pending_sell_proceeds - pending_buy_cost
    available_cash = portfolio.cash - pending_buy_cost

    current_prices = {sid: round_data[sid]["close"] for sid in stock_ids}
    total_value = portfolio.get_total_value(current_prices)
    delta = total_value - INITIAL_CAPITAL
    delta_pct = (delta / INITIAL_CAPITAL) * 100
    realized_pnl = portfolio.get_realized_pnl()
    unrealized_pnl = sum(
        (current_prices.get(sid, pos.avg_purchase_price) - pos.avg_purchase_price) * pos.quantity
        for sid, pos in portfolio.holdings.items()
    )

    c_val, c_cash, c_rpnl, c_upnl = responsive_columns(4, n_mobile=2)
    c_val.metric(
        "Nilai Portofolio",
        _format_rupiah(total_value),
        delta=f"{delta_pct:+.1f}%",
        delta_color="normal",
    )
    # Determine whether any non-hold orders are queued
    _has_active_orders = any(
        o.get("action_type") != "Tahan" for o in pending.values()
    ) if pending else False
    _net_sign = "+" if net_pending >= 0 else "−"
    _net_abs = abs(net_pending)

    c_cash.metric(
        "Kas Tersedia",
        _format_rupiah(portfolio.cash),   # always shows actual cash on hand
        delta=(
            f"Total Antrean: {_net_sign}{_format_rupiah(_net_abs)}"
            if _has_active_orders else " "
        ),
        delta_color="off",
        help=(
            "Kas tunai yang Anda miliki saat ini. "
            "'Total Antrean' adalah selisih neto semua order yang menunggu eksekusi "
            "(penjualan menambah, pembelian mengurangi)."
        ),
    )
    c_rpnl.metric(
        "Realized P&L",
        _format_rupiah(realized_pnl),
        delta=f"{realized_pnl:+,.0f}" if realized_pnl != 0 else " ",
        delta_color="normal",
    )
    c_upnl.metric(
        "Unrealized P&L",
        _format_rupiah(unrealized_pnl),
        delta=f"{unrealized_pnl:+,.0f}" if unrealized_pnl != 0 else " ",
        delta_color="normal",
    )

    # Guide expander
    with st.expander("Panduan Simulasi", expanded=False):
        st.markdown("""
**Cara bermain:**
- Setiap putaran mewakili **1 hari trading** menggunakan data historis saham IDX
- Pilih saham dari daftar di sebelah kiri, lalu lihat grafik harga dan indikator teknikal
- Tentukan keputusan: **Beli**, **Jual**, atau **Tahan** (default: Tahan)
- Klik **Tambahkan ke Antrean** untuk mencatat keputusan satu saham — ini belum mengeksekusi transaksi
- Setelah selesai memilih semua saham, klik **Eksekusi Semua** di bagian bawah untuk mengeksekusi semua antrean dan lanjut ke putaran berikutnya

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
    # On mobile, stack the two panels vertically — the [1, 3] desktop ratio
    # would otherwise crush the stock-picker into ~25% of a 380 px viewport
    # (~95 px), making the radio labels unreadable.
    # -----------------------------------------------------------------------
    col_left, col_right = responsive_columns([1, 3], n_mobile=1)

    with col_left:
        st.markdown("**Pilih Saham**")
        meta_map = st.session_state.get("stock_metadata", {})

        def _stock_label(sid: str) -> str:
            ticker = sid.split(".")[0]
            name = meta_map.get(sid, {}).get("name", "")
            price = current_prices.get(sid, 0)
            ret = round_data[sid].get("daily_return") or 0.0
            ret_str = f"+{ret*100:.1f}%" if ret >= 0 else f"{ret*100:.1f}%"
            held_badge = " 🔵" if sid in portfolio.holdings else ""
            return f"{ticker}{held_badge} [{_format_rupiah(price)}] ({ret_str})"

        selected_stock = st.radio(
            "Saham",
            options=stock_ids,
            format_func=_stock_label,
            key="selected_stock",
            label_visibility="collapsed",
        )

        st.divider()
        st.markdown("**Posisi Terbuka**")
        if portfolio.holdings:
            for sid_h, pos in portfolio.holdings.items():
                curr = current_prices.get(sid_h, pos.avg_purchase_price)
                # Per-position cash impact if closed now (+/− Rp vs entry).
                pnl = (curr - pos.avg_purchase_price) * pos.quantity
                proceeds = curr * pos.quantity
                icon = "🟢" if pnl >= 0 else "🔴"
                pnl_sign = "+" if pnl >= 0 else "−"
                st.caption(
                    f"{icon} **{sid_h.split('.')[0]}**: {pos.quantity} lbr "
                    f"@ {_format_rupiah(pos.avg_purchase_price)}  •  "
                    f"Kas bila ditutup: {_format_rupiah(proceeds)}  "
                    f"({pnl_sign}{_format_rupiah(abs(pnl))})"
                )

            projected = compute_projected_end_round_cash(portfolio, current_prices)
            st.caption(
                f"**Proyeksi Kas Akhir Ronde (jika semua posisi ditutup):** "
                f"{_format_rupiah(projected)}"
            )
        else:
            st.caption("Belum ada posisi terbuka")

        # Show pending orders in sidebar
        if pending:
            st.divider()
            st.markdown("**Keputusan Putaran Ini:**")
            # Simulate cash from scratch — start from actual portfolio.cash
            # so sell proceeds and buy costs are accounted once each.
            _sim_cash = portfolio.cash
            _has_non_hold = False
            for sid_o, order in pending.items():
                ticker_label = sid_o.split(".")[0]
                price = current_prices.get(sid_o, 0.0)
                qty = order.get("quantity", 0)
                atype = order["action_type"]

                if atype == "Tahan":
                    pass   # Hold is default — not shown in the order summary
                elif atype == "Jual" and qty > 0 and price > 0:
                    proceeds = price * qty
                    _sim_cash += proceeds
                    _has_non_hold = True
                    st.caption(f"**{ticker_label}**: Jual {qty} lbr (+Rp {proceeds:,.0f})")
                elif atype == "Beli" and qty > 0 and price > 0:
                    cost = price * qty
                    _sim_cash -= cost
                    _has_non_hold = True
                    st.caption(f"**{ticker_label}**: Beli {qty} lbr (−Rp {cost:,.0f})")
                else:
                    st.caption(f"**{ticker_label}**: {atype} {qty} lbr")

            # Final estimated cash — only show when there are actionable orders
            if _has_non_hold:
                _color = "color:#0F9D58;" if _sim_cash >= 0 else "color:#D93025;"
                st.markdown(
                    f"<div style='font-size:12px; margin-top:6px; {_color}'>"
                    f"<b>Estimasi kas setelah eksekusi: Rp {_sim_cash:,.0f}</b></div>",
                    unsafe_allow_html=True,
                )

    with col_right:
        sid = selected_stock
        snap = round_data[sid]
        pre_hist = pre_history_all.get(sid, [])
        win_data = window[sid]
        meta = meta_map.get(sid, {})
        ticker = sid.split(".")[0]

        # Stock header — STOCK-01
        desc_map = st.session_state.get("stock_descriptions", {})
        stock_info = desc_map.get(sid, {})
        vol_class = stock_info.get("volatility_class", "")
        description = stock_info.get("description", "")

        _VOL_LABEL = {
            "low": ("Stabil", "#50c88c"),
            "low_medium": ("Cukup Stabil", "#6c8fff"),
            "medium": ("Moderat", "#ffbe3c"),
            "high": ("Volatil", "#ff7070"),
        }
        vol_label, vol_color = _VOL_LABEL.get(vol_class, ("—", "#8b8fa8"))

        hdr_col, badge_col = responsive_columns([5, 1], n_mobile=1)
        with hdr_col:
            st.markdown(
                f"**{ticker}** — {meta.get('name', '')} "
                f"*({meta.get('sector', '')})*"
            )
        with badge_col:
            st.markdown(
                f"<div style='text-align:right; padding-top:4px;'>"
                f"<span style='color:{vol_color}; font-size:11px; font-weight:600;'>"
                f"● {vol_label}</span></div>",
                unsafe_allow_html=True,
            )
        if description:
            st.caption(description)

        # Technical indicators row (above chart so users read them before the chart shapes perception)
        ma5 = snap.get("ma_5")
        ma20 = snap.get("ma_20")
        trend = snap.get("trend") or "—"
        rsi = snap.get("rsi_14")
        daily_ret = snap.get("daily_return")
        ret_str = f"{daily_ret * 100:+.2f}%" if daily_ret is not None else "—"

        ind_cols = responsive_columns(4, n_mobile=2)
        ind_cols[0].metric(
            "Harga Penutupan",
            _format_rupiah(snap["close"]),
            delta=ret_str,
            help="Harga penutupan hari ini. Delta menunjukkan perubahan dari hari sebelumnya.",
        )
        ind_cols[1].metric(
            "MA5",
            _format_rupiah(ma5) if ma5 else "—",
            help=(
                "Moving Average 5 Hari: rata-rata harga penutupan 5 hari terakhir. "
                "Jika harga saat ini di ATAS MA5, momentum jangka pendek cenderung positif. "
                "Jika di BAWAH MA5, momentum melemah."
            ),
        )
        ind_cols[2].metric(
            "MA20",
            _format_rupiah(ma20) if ma20 else "—",
            help=(
                "Moving Average 20 Hari: tren jangka menengah. "
                "Persilangan MA5 memotong ke atas MA20 (golden cross) sering dilihat sebagai sinyal beli. "
                "MA5 memotong ke bawah MA20 (death cross) sering dilihat sebagai sinyal jual."
            ),
        )
        rsi_str = f"{rsi:.0f}" if rsi is not None else "—"
        ind_cols[3].metric(
            "RSI-14",
            rsi_str,
            delta=trend.capitalize() if trend and trend != "—" else None,
            delta_color="off",
            help=(
                "Relative Strength Index (14 hari): mengukur kecepatan dan besar perubahan harga. "
                "RSI > 70: kondisi overbought — harga mungkin terlalu tinggi dan bisa koreksi. "
                "RSI < 30: kondisi oversold — harga mungkin terlalu rendah dan bisa rebound. "
                "RSI 30–70: zona netral."
            ),
        )

        st.divider()

        # Mobile-friendly chart toggle. Defaults to ON when global Mode mobile
        # is active; user can override per-chart. Falls back to candlestick
        # otherwise.
        compact_default = is_mobile()
        compact = st.toggle(
            "Tampilan ringkas untuk mobile",
            value=compact_default,
            key=f"chart_compact_{sid}",
            help=(
                "Aktifkan untuk grafik garis sederhana yang lebih mudah dibaca "
                "di layar telepon. Lintasan harga dan batas mulai trading tetap "
                "ditampilkan."
            ),
        )
        fig = _build_full_chart(sid, pre_hist, win_data, current_round, compact=compact)
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{sid}_{current_round}")

        # Current position info
        held = portfolio.holdings.get(sid)
        if held:
            pos_pnl = (snap["close"] - held.avg_purchase_price) * held.quantity
            pos_pnl_sign = "+" if pos_pnl >= 0 else ""
            st.caption(
                f"📌 Posisi: **{held.quantity} lbr** @ {_format_rupiah(held.avg_purchase_price)} "
                f"| P&L: {pos_pnl_sign}{_format_rupiah(pos_pnl)}"
            )

        # Order panel — the action radio sits OUTSIDE the form so the submit
        # button label stays reactive to Beli/Jual/Tahan toggles.
        st.markdown(f"**Keputusan untuk {ticker}**")

        existing_order = pending.get(sid, {})
        action_options = ["Tahan", "Beli", "Jual"]
        default_action_idx = 0
        if existing_order.get("action_type") in action_options:
            default_action_idx = action_options.index(existing_order["action_type"])

        action_type = st.radio(
            "Aksi",
            action_options,
            index=default_action_idx,
            horizontal=True,
            key=f"action_radio_{sid}_{current_round}",
        )
        # Expose current action in session state so helpers (and the reactive
        # confirm button label) can read it on every rerun.
        st.session_state["pending_action"] = {
            "Beli": "buy", "Jual": "sell", "Tahan": "hold",
        }[action_type]
        st.session_state["pending_ticker"] = ticker

        with st.form(f"order_{current_round}_{sid}", clear_on_submit=False):
            held = portfolio.holdings.get(sid)
            quantity = 0
            if action_type == "Beli":
                # If this stock already has a pending buy, its cost is already
                # deducted from available_cash. Refund it so the user can keep
                # or increase their existing order without it being silently capped.
                _existing_buy_qty = (
                    existing_order.get("quantity", 0)
                    if existing_order.get("action_type") == "Beli" else 0
                )
                _refund = _existing_buy_qty * snap["close"]
                max_buy = int((available_cash + _refund) // snap["close"]) if snap["close"] > 0 else 0
                default_qty = _existing_buy_qty
                quantity = st.number_input(
                    "Jumlah lembar",
                    min_value=0,
                    max_value=max(max_buy, 0),
                    value=min(default_qty, max_buy),
                    step=1,
                    key=f"qty_buy_form_{sid}_{current_round}",
                )
                if quantity > 0:
                    cost = quantity * snap["close"]
                    st.caption(f"Estimasi biaya: {_format_rupiah(cost)}")
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
                    proceeds = quantity * snap["close"]
                    remaining_qty = held.quantity - quantity
                    st.caption(f"Estimasi P&L: {pnl_sign}{_format_rupiah(pnl_est)}")
                    st.caption(
                        f"Sisa posisi: {remaining_qty} lbr" if remaining_qty > 0
                        else "Posisi akan ditutup sepenuhnya."
                    )
            else:
                st.caption("Anda memilih **Tahan** — tidak ada transaksi untuk saham ini.")

            btn_label = build_order_button_label(action_type, ticker)
            order_submitted = st.form_submit_button(btn_label, use_container_width=True)

        if order_submitted:
            if action_type == "Beli" and quantity > 0:
                pending[sid] = {"action_type": "Beli", "quantity": quantity}
            elif action_type == "Jual" and quantity > 0:
                pending[sid] = {"action_type": "Jual", "quantity": quantity}
            else:
                pending[sid] = {"action_type": "Tahan", "quantity": 0}
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
