# CDT Bias Detection System
### Sistem Deteksi dan Mitigasi Bias Perilaku bagi Investor Ritel di Pasar Modal Indonesia

A **Cognitive Digital Twin (CDT)** system that detects behavioral biases in retail investors
through simulated trading with historical IDX stock data.

---

## Quick Start

### Prerequisites
- Python 3.11+
- pip

### One-command setup
```bash
bash setup.sh
```

### Manual setup
```bash
git clone https://github.com/arvynopl/TA-18222007.git
cd TA-18222007
pip install -r requirements.txt
```

### Run
```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

### For UAT Participants
See [UAT_GUIDE.md](UAT_GUIDE.md) for step-by-step instructions in Bahasa Indonesia.

---

## System Overview

The system implements a 5-stage pipeline repeated over multiple sessions:

```
Simulation (14 rounds × 6 IDX stocks)
    → Action Logging (UserAction table)
        → Feature Extraction (SessionFeatures)
            → Bias Metrics (DEI, OCS, LAI)
                → CDT Profile Update (EMA)
                    → Personalized Feedback
```

### Three Detected Biases

| Bias | Formula | Severe | Moderate | Mild |
|------|---------|--------|----------|------|
| **Disposition Effect (DEI)** | PGR − PLR (Odean 1998) | > 0.50 | > 0.15 | > 0.05 |
| **Overconfidence (OCS)** | sigmoid(trade_freq / perf_ratio) (Barber & Odean 2000) | > 0.70 | > 0.40 | > 0.20 |
| **Loss Aversion (LAI)** | avg_hold_losers / avg_hold_winners (Kahneman & Tversky 1979) | > 2.00 | > 1.50 | > 1.20 |

### CDT Update (Exponential Moving Average)

```
BiasIntensity(t) = α × BiasMetric(t) + (1−α) × BiasIntensity(t−1)    [α = 0.3]
RiskPreference(t) = β × ObservedRisk(t) + (1−β) × RiskPreference(t−1) [β = 0.2]
StabilityIndex(t) = 1 − mean(σ_OCS, σ_DEI, σ_LAI) over last 5 sessions
```

### Stock Universe (6 IDX Stocks)

| Ticker | Company | Sector | Volatility |
|--------|---------|--------|-----------|
| BBCA.JK | Bank Central Asia | Finance | Low |
| TLKM.JK | Telkom Indonesia | Telecom | Low-Medium |
| ANTM.JK | Aneka Tambang | Mining | High |
| GOTO.JK | GoTo Gojek Tokopedia | Technology | High |
| UNVR.JK | Unilever Indonesia | Consumer | Medium |
| BBRI.JK | Bank Rakyat Indonesia | Finance | Medium |

---

## Architecture

```
app.py                      Streamlit entry point (5 pages)
config.py                   All thresholds and tunable parameters
database/
  models.py                 9 ORM entities (SQLAlchemy 2.0)
  connection.py             Session factory and DB init
  seed.py                   Stock catalog + market snapshot seeding
modules/
  simulation/               UI, engine (historical replay), portfolio
  logging_engine/           Action logger, session validator
  analytics/                Bias metrics, feature extraction
  cdt/                      CDT profile CRUD, EMA updater, stability
  feedback/                 Template-based feedback generator + renderer
  utils/                    Data export helpers
tests/                      pytest suite (85 tests)
data/
  stock_catalog.json        6 IDX stock definitions
  all_market_snapshots.csv  ~2826 rows of OHLCV + indicators
```

### Database Entities

| Entity | Purpose |
|--------|---------|
| User | Investor identified by alias |
| StockCatalog | 6 IDX stock metadata |
| MarketSnapshot | Daily OHLCV + MA5/MA20/RSI |
| UserAction | Every buy/sell/hold decision |
| BiasMetric | Computed OCS, DEI, LAI per session |
| CognitiveProfile | EMA-updated bias intensity vector |
| FeedbackHistory | Delivered feedback text per session |
| ConsentLog | UAT participant consent audit trail |
| SessionSummary | Session lifecycle tracking |

---

## Running Tests

```bash
pytest tests/ -v
```

Target: **85 tests passing, 0 failures**.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| UI | Streamlit |
| Backend | Python 3.11+ |
| Database | SQLite (dev) / PostgreSQL (prod via `CDT_DATABASE_URL` env var) |
| ORM | SQLAlchemy 2.0+ |
| Charts | Plotly |
| Testing | pytest |

---

## Configuration

Key parameters in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `INITIAL_CAPITAL` | Rp 10,000,000 | Starting portfolio value |
| `ROUNDS_PER_SESSION` | 14 | Trading rounds per simulation session |
| `ALPHA` | 0.3 | EMA weight for bias intensity |
| `BETA` | 0.2 | EMA weight for risk preference |
| `CDT_STABILITY_WINDOW` | 5 | Sessions used for stability index |

Override the database URL for production:
```bash
export CDT_DATABASE_URL="postgresql://user:pass@host/dbname"
streamlit run app.py
```

---

## Research Context

This system is developed as part of a final thesis at
**Institut Teknologi Bandung (ITB)**, School of Electrical Engineering and Informatics (STEI),
Information Systems and Technology program.

**Author:** Arvyno Pranata Limahardja (NIM: 18222007)
**Supervisor:** Prof. Dr. Ir. Suhono Harso Supangkat, M.Eng.

---

## License

This project is part of an academic thesis. All rights reserved.
