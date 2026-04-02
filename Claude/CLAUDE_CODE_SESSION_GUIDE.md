# CLAUDE CODE — Session Execution Guide
# How to use the master prompt efficiently across multiple Claude Code sessions

## PRINCIPLE: Never paste the entire master prompt in one go.

The master prompt is a REFERENCE DOCUMENT. Each Claude Code session should receive
only the relevant section + minimal context. This maximizes token efficiency.

---

## SESSION 1: Project Scaffold + Database (Est: 15-20 min)
**Model: Sonnet 4.6 | Thinking: OFF**

### Paste this prompt:
```
Create a Python project for a CDT bias detection system with this structure:

cdt-bias-detection/
├── app/__init__.py
├── app/config.py
├── app/models/__init__.py
├── app/models/database.py      # SQLAlchemy engine, SQLite for dev
├── app/models/entities.py      # 7 ORM models (see schema below)
├── app/modules/__init__.py
├── app/services/__init__.py
├── app/ui/__init__.py
├── data/market/                # empty, will hold CSV files
├── tests/__init__.py
├── tests/test_entities.py
├── requirements.txt
└── README.md

[PASTE only the DATABASE SCHEMA section from master prompt]
[PASTE only requirements: streamlit, sqlalchemy, pandas, numpy, plotly, scikit-learn, pytest]

Config should include: ALPHA=0.3, BETA=0.2, INITIAL_CAPITAL=10_000_000,
ROUNDS_PER_SESSION=14, and all bias severity thresholds.

Write test_entities.py to verify all 7 tables create correctly and basic CRUD works.
Run the tests.
```

### Verify before moving on:
- [ ] `pytest tests/test_entities.py -v` passes
- [ ] Database creates with all 7 tables

---

## SESSION 2: Market Data Service (Est: 10-15 min)
**Model: Sonnet 4.6 | Thinking: OFF**

### Paste this prompt:
```
In the cdt-bias-detection project, create:

1. app/services/market_data.py
   - Function: load_csv_to_db(csv_dir: str) → seeds StockCatalog + MarketSnapshot from CSV files
   - Function: get_snapshots(stock_id: int, start_date, end_date) → list[MarketSnapshot]
   - Function: get_stock_catalog() → list[StockCatalog]
   - CSVs have columns: Date, Open, High, Low, Close, Volume, MA_5, MA_20, RSI_14
   - Stock catalog CSV has: ticker, name, sector, volatility_class, liquidity_class, bias_role

2. app/services/scenario_manager.py
   - Function: select_scenario_window(stock_id, window_type="random"|"crash"|"rally"|"high_volatility", window_size=14) → list[MarketSnapshot]
   - Uses scenario_windows.csv if available, otherwise selects random 14-day window
   - Function: get_all_stocks_window(start_date, window_size=14) → dict[stock_id, list[MarketSnapshot]]

Test with the CSV files in data/market/ directory.
```

---

## SESSION 3: Simulation Module + Logging (Est: 30-40 min)
**Model: Sonnet 4.6 | Thinking: OFF**

### Paste this prompt:
```
In the cdt-bias-detection project, create the Simulation Module:

1. app/modules/simulation.py
   - Class: SimulationSession
     - __init__(user_id, session_id, stocks, snapshots_per_stock, initial_capital=10_000_000)
     - Properties: current_round, portfolio (cash + holdings), is_complete
     - Method: execute_action(stock_id, action_type, quantity) → records action, updates portfolio
     - Method: advance_round() → moves to next round
     - Method: get_portfolio_value() → current total value (cash + holdings at market price)
     - Method: get_portfolio_pnl() → per-position profit/loss
     - Portfolio tracks: Position(stock_id, quantity, purchase_price, purchase_round)

2. app/modules/logging_engine.py
   - Function: log_action(session, user_id, session_id, stock_id, snapshot_id, action_type, quantity, response_time_ms) → writes UserAction to DB
   - Validates: action_type in (buy, sell, hold), quantity >= 0, sufficient cash/holdings
   - Returns logged UserAction or raises ValueError

3. app/ui/simulation_view.py — Streamlit page:
   - Header: round counter (e.g., "Putaran 3 dari 14"), portfolio value, cash remaining
   - For each stock: price card showing current price, MA_5, MA_20, mini Plotly chart (last 20 days)
   - Per-stock action controls: radio (Beli/Jual/Tahan) + quantity input
   - "Eksekusi Keputusan" button → logs all actions, advances round
   - After round 14: "Sesi Selesai" → triggers analytics pipeline
   - Timer: track response_time_ms from page load to action submission
   - Language: ALL UI text in Bahasa Indonesia

4. tests/test_simulation.py
   - Test: 14-round session completes correctly
   - Test: buy reduces cash, increases holdings
   - Test: sell increases cash, reduces holdings
   - Test: cannot sell more than held, cannot buy more than affordable
   - Test: portfolio value calculation is correct
```

---

## SESSION 4: Analytics Engine (Est: 20-30 min)
**Model: Sonnet 4.6 | Thinking: OFF**

### Paste this prompt:
```
In the cdt-bias-detection project, create the Analytics Engine:

app/modules/analytics_engine.py

[PASTE the CORE ALGORITHMS — Analytics Engine section from master prompt]

Additional requirements:
- Function: compute_all_metrics(user_id, session_id) → BiasMetric
  - Queries UserAction + MarketSnapshot for the session
  - Computes OCS, PGR, PLR, DEI, LAI
  - Saves BiasMetric to database
  - Returns the BiasMetric object

- Helper functions (implement these):
  - count_sales_at_profit(actions, snapshots): count sell actions where sell price > purchase price
  - count_sales_at_loss(actions, snapshots): count sell actions where sell price < purchase price
  - count_unsold_at_profit(portfolio, current_prices): positions still held with positive P&L
  - count_unsold_at_loss(portfolio, current_prices): positions still held with negative P&L
  - holding_duration(action): rounds held from purchase to sale
  - sold_at_profit/sold_at_loss: filter sold positions by P&L

tests/test_analytics.py — Create 4 synthetic test profiles:
1. "Overconfident": 12 trades in 14 rounds, portfolio drops 15% → expect OCS > 0.6
2. "Disposition": sells 4/5 winners, sells 0/3 losers → expect PGR > 0.7, PLR < 0.1, DEI > 0.5
3. "Loss-averse": holds losers avg 8 rounds, winners avg 3 rounds → expect LAI > 2.0
4. "Balanced": moderate trading, mixed sales → expect all metrics near baseline

All formulas must have docstrings citing the academic source (Odean 1998, Barber & Odean 2000, Kahneman & Tversky 1979).
```

---

## SESSION 5: CDT Engine (Est: 15-20 min)
**Model: Sonnet 4.6 | Thinking: OFF**

### Paste this prompt:
```
In the cdt-bias-detection project, create the CDT Engine:

app/modules/cdt_engine.py

[PASTE the CORE ALGORITHMS — CDT Engine section from master prompt]

Requirements:
- Function: get_or_create_profile(user_id) → CognitiveProfile
- Function: update_profile(user_id, metrics: BiasMetric) → CognitiveProfile
  - Implements EMA update with ALPHA=0.3 for bias intensities
  - Updates risk_preference with BETA=0.2
  - Computes stability_index from last 5 sessions
  - Persists to database
- Function: get_profile_history(user_id) → list of historical BiasMetric values

tests/test_cdt.py:
- Test: new user gets default profile (all zeros, session_count=0)
- Test: after 1 session with high overconfidence, bias_intensity_overconfidence = ALPHA * OCS
- Test: after 5 identical sessions, profile converges toward the constant values
- Test: stability_index increases when bias pattern is consistent across sessions
- Test: stability_index decreases when bias pattern is erratic
```

---

## SESSION 6: Feedback Engine (Est: 15-20 min)
**Model: Sonnet 4.6 | Thinking: OFF**

### Paste this prompt:
```
In the cdt-bias-detection project, create the Feedback Engine:

app/modules/feedback_engine.py

[PASTE the FEEDBACK_TEMPLATES dict and classify_severity function from master prompt]

Requirements:
- Function: generate_feedback(user_id, session_id, metrics: BiasMetric, profile: CognitiveProfile, session_actions, snapshots) → list[FeedbackHistory]
  - For each bias type: classify severity, select template, fill slots with actual values
  - Compute counterfactual values where applicable (e.g., "if you held X for N more rounds...")
  - Save all FeedbackHistory records to database
  - Return the list

- Function: get_session_feedback(user_id, session_id) → list[FeedbackHistory]
- Function: get_longitudinal_summary(user_id) → dict with trend info across sessions

app/ui/feedback_view.py — Streamlit page:
  - For each detected bias: expandable section with severity badge (color-coded)
  - Show explanation text and recommendation text
  - If user has >1 session: show longitudinal comparison ("Sesi sebelumnya: DEI=0.65 → Sesi ini: DEI=0.35")
  - All text in Bahasa Indonesia

tests/test_feedback.py:
- Test: severe overconfidence → correct template selected
- Test: no disposition effect (DEI < 0.05) → severity = "none", no feedback generated for this bias
- Test: feedback text contains actual metric values (not template placeholders)
```

---

## SESSION 7: Integration + Main App (Est: 30-40 min)
**Model: Sonnet 4.6 | Thinking: OFF**

### Paste this prompt:
```
In the cdt-bias-detection project, wire everything together:

1. app/main.py — Streamlit multi-page app:
   - Page 1: "Simulasi Investasi" → simulation_view (create user alias → run 14 rounds)
   - Page 2: "Hasil Analisis" → feedback_view (shown after session completes)
   - Page 3: "Profil Kognitif" → dashboard_view (CDT profile summary)
   - Sidebar: user info, session history, navigation

2. app/ui/dashboard_view.py:
   - Plotly radar/spider chart: 3 axes (overconfidence, disposition, loss_aversion) showing bias intensity from CognitiveProfile
   - Session-over-session line chart: bias metrics trend across sessions
   - StabilityIndex display, RiskPreference display
   - All in Bahasa Indonesia

3. Full pipeline wiring (in simulation_view.py after round 14):
   - analytics_engine.compute_all_metrics(user_id, session_id)
   - cdt_engine.update_profile(user_id, metrics)
   - feedback_engine.generate_feedback(user_id, session_id, metrics, profile, actions, snapshots)
   - Auto-navigate to feedback_view

4. tests/test_integration.py:
   - Programmatically run 3 sessions with scripted actions (no UI)
   - Verify: BiasMetric values computed for each session
   - Verify: CognitiveProfile updates 3 times with EMA convergence
   - Verify: FeedbackHistory has entries for all 3 sessions
   - Verify: StabilityIndex changes between session 1 and session 3

Run the full test suite: pytest tests/ -v
Then run: streamlit run app/main.py — verify the app launches and basic flow works.
```

---

## SESSION 8: Polish + Bug Fix (Est: 20 min)
**Model: Sonnet 4.6 | Thinking: OFF**

### Use for:
- Fix any bugs from integration testing
- UI polish (spacing, Bahasa text corrections)
- Edge cases (what if user holds nothing? what if only 1 trade in session?)
- Add error handling for empty portfolios, division by zero in metrics

---

## SESSION 9: Thesis Writing Assistance
**Model: Opus 4.6 | Extended Thinking: ON**

### Use for:
- Drafting Bab V (Implementation chapter) — describe architecture decisions, code structure
- Drafting Bab VI (Evaluation) — methodology, results tables, analysis
- Academic Bahasa Indonesia prose with proper formal register
- Generating properly formatted LaTeX tables for test results

---

## EMERGENCY: If running out of Claude usage

Priority order if you must cut sessions:
1. Sessions 1-4 are NON-NEGOTIABLE (foundation + analytics = thesis core)
2. Session 5 (CDT) is CRITICAL (this is the academic contribution)
3. Session 6 (Feedback) can use simplified templates (reduce to 3 hardcoded strings per bias)
4. Session 7 (Integration) can be done manually by following the wiring steps
5. Sessions 8-9 can be done with manual effort

The minimum viable Claude Code usage is Sessions 1-5 (~2-3 hours of Claude time).
