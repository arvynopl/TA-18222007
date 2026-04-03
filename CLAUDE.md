# CDT Bias Detection System — Developer Context for Claude Code

## Project Identity
Thesis project (TA-18222007), Institut Teknologi Bandung, Information Systems & Technology.
Builds a Cognitive Digital Twin (CDT) for detecting retail investor behavioral biases.
Author: Arvyno Pranata Limahardja (NIM: 18222007).

## Key Commands
```bash
streamlit run app.py          # Run the app (opens at http://localhost:8501)
pytest tests/ -v              # Run full test suite (target: 85 passed, 0 failed)
pytest tests/ -v --tb=short   # Run with compact failure output
python -m database.seed       # Re-seed the database (idempotent)
bash setup.sh                 # One-command first-time setup
```

## Architecture Map
```
app.py                   Streamlit entry point — 5 pages, routing, session state
config.py                ALL tunable parameters and thresholds (edit here, not in modules)
database/
  models.py              9 SQLAlchemy ORM entities + indexes
  connection.py          get_session() context manager, init_db()
  seed.py                seed_stock_catalog(), seed_market_snapshots(), run_seed()
modules/
  simulation/
    ui.py                render_simulation_page(), _build_price_chart()
    engine.py            SimulationEngine — random 14-day window selection
    portfolio.py         Portfolio, Position, SoldTrade — pure Python, no DB/Streamlit
  logging_engine/
    logger.py            log_action(), log_hold()
    validator.py         validate_session_completeness()
  analytics/
    features.py          SessionFeatures dataclass, extract_session_features()
    bias_metrics.py      compute_disposition_effect/overconfidence/loss_aversion, classify_severity
  cdt/
    profile.py           get_or_create_profile()
    updater.py           update_profile() — EMA update
    stability.py         compute_stability_index()
  feedback/
    generator.py         generate_feedback(), compute_counterfactual()
    templates.py         TEMPLATES dict: 3 biases × 4 severity levels (none/mild/moderate/severe)
    renderer.py          render_feedback_page() — Streamlit rendering
  utils/
    export.py            export_session_to_dict(), export_user_history_csv(), export_session_data()
tests/
  conftest.py            Shared db/user fixtures (in-memory SQLite)
  test_bias_metrics.py   Unit tests for bias formulas + classify_severity
  test_cdt_updater.py    EMA convergence + stability index tests
  test_feedback.py       Feedback generation + template tests
  test_integration.py    End-to-end pipeline tests
  test_simulation.py     Portfolio unit tests
  test_validator.py      Session completeness validation
  test_features.py       SessionFeatures extraction
  test_counterfactual.py compute_counterfactual edge cases
  test_portfolio_extended.py  Additional Portfolio scenarios
  test_export.py         Data export utility tests
```

## Bias Formulas (DO NOT CHANGE)
- **DEI** = PGR − PLR  (Odean, 1998)
  - PGR = Realized_Gains / (Realized_Gains + Paper_Gains)
  - PLR = Realized_Losses / (Realized_Losses + Paper_Losses)
- **OCS** = sigmoid(trade_frequency / max(performance_ratio, 0.01))  (Barber & Odean, 2000)
- **LAI** = avg_hold_losers / max(avg_hold_winners, 1.0)  (Kahneman & Tversky, 1979)
- **EMA**: BiasIntensity(t) = 0.3 × metric(t) + 0.7 × BiasIntensity(t−1)

## Severity Thresholds (in config.py)
| Bias | Mild | Moderate | Severe |
|------|------|----------|--------|
| DEI  | 0.05 | 0.15     | 0.50   |
| OCS  | 0.20 | 0.40     | 0.70   |
| LAI  | 1.20 | 1.50     | 2.00   |

## Coding Conventions
- **Language**: All UI text, feedback templates, and user-facing strings in **Bahasa Indonesia**
- **Datetime**: always `datetime.now(timezone.utc)` — never `datetime.utcnow()`
- **DB session**: use `with get_session() as sess:` — never hold sessions across Streamlit reruns
- **Tests**: in-memory SQLite, use `conftest.py` fixtures, never import Streamlit in tests
- **Logging**: `logger = logging.getLogger(__name__)` at module level; use `logger.debug/info/warning`

## Do NOT
- Change the tech stack (Streamlit, SQLAlchemy, pandas, Plotly, pytest)
- Add new biases beyond DEI, OCS, LAI
- Add LLM/RAG to feedback (documented as future work)
- Restructure the folder layout or rename modules
- Use `datetime.utcnow()` (deprecated)
- Use `print()` in production code (use logging)
- Commit `*.db` files (they are gitignored)

## Environment Variable
```bash
export CDT_DATABASE_URL="sqlite:///path/to/db.db"   # override default
export CDT_DATABASE_URL="postgresql://..."           # for production
```
