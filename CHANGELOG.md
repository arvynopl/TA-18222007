# CHANGELOG

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.3.0] — 2026-04-03 — UI/UX Overhaul & Critical Bug Fixes

### Fixed (Critical)
- **Bug A** (`simulation/ui.py`): `sim_engine` session_state key was never set, causing the window to re-randomize on every Streamlit rerun. Stock prices changed whenever the user clicked +/- on quantity inputs. Fixed by storing a boolean flag after window initialization.
- **Bug B** (`feedback/renderer.py`): `DetachedInstanceError` on the feedback page — ORM objects were accessed outside the SQLAlchemy session. Fixed by serializing feedback rows to plain dicts inside the `with get_session()` block.
- **Bug C** (`simulation/ui.py`): Quantity input rerun instability — each widget interaction triggered a full page rerun. Fixed by wrapping order controls in per-stock `st.form()`, batching all inputs and only submitting once.

### Added — Simulation UI (Trading Platform Paradigm)
- `simulation/ui.py`: Complete rewrite with trading-platform layout (left sidebar + right chart/order panel)
- `simulation/ui.py`: Candlestick chart (`_build_full_chart`) showing 30 days of pre-window history (dimmed) + trading window (colored), with MA5/MA20 overlays and "Mulai Trading" vertical marker
- `simulation/ui.py`: Stock selector radio in left sidebar — users view one stock at a time
- `simulation/ui.py`: Per-stock order form (`st.form`) with Beli/Jual/Tahan radio, quantity input, estimated cost/P&L caption
- `simulation/ui.py`: Pending orders accumulator — users confirm per-stock decisions, then execute all with a single "Eksekusi Semua" button
- `simulation/ui.py`: `_execute_round()` helper — auto-logs "hold" for all non-interacted stocks
- `simulation/ui.py`: Panduan Simulasi expander with candlestick reading guide in Bahasa Indonesia
- `simulation/ui.py`: Holdings summary sidebar with P&L per open position
- `simulation/engine.py`: `get_pre_window_history()` method — fetches `PRE_WINDOW_DAYS` of data before the trading window start date

### Added — Stock Universe (6 → 12 stocks)
- `data/stock_catalog.json`: Added ASII.JK, BMRI.JK, ICBP.JK, MDKA.JK, BRIS.JK, EMTK.JK
- `idx_data_acquisition.py`: New data download script covering all 12 IDX tickers (run manually)
- `config.py`: `PRE_WINDOW_DAYS = 30` constant

### Added — Tests
- `tests/test_free_choice.py`: 5 new tests for free-choice trading (partial stock coverage, auto-hold, full pipeline)
- `tests/test_integration.py`: `test_full_pipeline_with_twelve_stocks` for the expanded 12-stock universe
- `tests/conftest.py`: Updated to 12 stocks and 50 days of snapshots per stock

### Changed
- `tests/conftest.py`: Expanded from 6 to 12 stocks; snapshot count bumped 20 → 50 days
- `tests/test_integration.py`: Action count assertion uses `14 * len(STOCKS)` (generalized)

---

## [0.2.0] — 2026-04-03 — Hardening & UAT-Readiness Pass

### Fixed
- `app.py`: corrected mismatched Markdown asterisks in Beranda page description (`**Umpan Balik*` → `**Umpan Balik**`)
- `database/seed.py`: removed redundant `print()` call that duplicated `logger.info()` output

### Added — Backend
- `config.py`: `DEI_MILD`, `OCS_MILD`, `LAI_MILD` thresholds for 4-level severity classification
- `config.py`: `DATABASE_URL` reads from `CDT_DATABASE_URL` environment variable (default: local SQLite)
- `bias_metrics.py`: `classify_severity()` extended with optional `mild_t` parameter; backward-compatible
- `bias_metrics.py`: detailed sigmoid normalization comment with threshold calibration examples (Barber & Odean 2000)
- `bias_metrics.py`, `generator.py`, `updater.py`: `logging.getLogger(__name__)` and debug-level log statements for key computations
- `models.py`: composite `Index` on `(user_id, session_id)` for `UserAction`, `BiasMetric`, `FeedbackHistory`
- `models.py`: `cascade="all, delete-orphan"` on all `User` child relationships
- `models.py`: `ConsentLog` entity for UAT consent audit trail
- `models.py`: `SessionSummary` entity for session lifecycle tracking
- `modules/utils/export.py`: `export_session_to_dict`, `export_user_history_csv`, `export_session_data` (CSV per table)

### Added — Frontend
- `simulation/ui.py`: MA5/MA20 overlay traces on Plotly price charts (dashed orange / dotted green)
- `app.py`: `_page_consent()` — UAT research information and consent checkbox page in Bahasa Indonesia
- `app.py`: consent gate on Beranda and Simulasi pages (requires `consent_given = True`)
- `app.py`: session history summary (count + last date) on Beranda for logged-in users
- `app.py`: risk preference qualitative label (Konservatif/Moderat/Agresif) with expander explanation
- `app.py`: `consent_given` key in `_init_session_state()`

### Added — CDT
- `features.py`: `avg_response_time_ms`, `max_response_time_ms`, `portfolio_return_pct` fields on `SessionFeatures`

### Added — Tests
- `tests/conftest.py`: shared `db`/`user` fixtures (in-memory SQLite + 6 stocks + 20 snapshots)
- `tests/test_validator.py`: 5 tests for `validate_session_completeness`
- `tests/test_features.py`: 5 tests for `extract_session_features` and new timing/return fields
- `tests/test_counterfactual.py`: 4 tests for `compute_counterfactual` edge cases
- `tests/test_portfolio_extended.py`: 5 tests for `Portfolio` (open positions, partial sell, multi-buy)
- `tests/test_export.py`: 5 tests for data export utilities
- `tests/test_integration.py`: `test_mild_severity_classification()` end-to-end mild path
- `tests/test_bias_metrics.py`: 3 tests for `classify_severity` mild level
- **Total: 85 tests passing, 0 failures**

### Added — Documentation
- `README.md`: comprehensive project documentation (architecture, biases, stack, config)
- `UAT_GUIDE.md`: step-by-step participant guide in Bahasa Indonesia
- `CHANGELOG.md`: this file
- `CLAUDE.md`: developer context for Claude Code sessions
- `.gitignore`: extended with `*.db`, `*.sqlite3`, `.env`, `venv/`, `exports/`
- `setup.sh`: one-command setup script

### Added — Security
- `app.py`: alias input validation (alphanumeric + spaces, 2–64 characters)

---

## [0.1.0] — 2025 — Initial MVP

### Added
- Multi-page Streamlit application with 4 pages (Beranda, Simulasi, Hasil Analisis, Profil Kognitif)
- 14-round simulation engine with historical IDX market data replay
- 6 IDX stocks: BBCA, TLKM, ANTM, GOTO, UNVR, BBRI
- Disposition Effect (DEI), Overconfidence (OCS), Loss Aversion (LAI) bias metrics
- Cognitive Digital Twin profile with EMA update (α=0.3, β=0.2)
- Template-based feedback generation in Bahasa Indonesia (9 templates: 3 biases × 3 severity levels)
- SQLAlchemy ORM with 7 entities; SQLite default, PostgreSQL-ready
- pytest test suite covering unit and integration scenarios
