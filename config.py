"""
config.py — Central configuration for the CDT Bias Detection System.

All tunable parameters, thresholds, and paths are defined here.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = f"sqlite:///{BASE_DIR / 'cdt_bias.db'}"

# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------
INITIAL_CAPITAL: float = 10_000_000.0   # Rp 10,000,000
ROUNDS_PER_SESSION: int = 14

# ---------------------------------------------------------------------------
# CDT update weights (EMA)
# ---------------------------------------------------------------------------
ALPHA: float = 0.3   # Recency weight for bias intensity vector
BETA: float = 0.2    # Recency weight for risk preference
CDT_STABILITY_WINDOW: int = 5  # Number of past sessions used for stability index

# ---------------------------------------------------------------------------
# Bias severity thresholds
# ---------------------------------------------------------------------------
# Disposition Effect Index (DEI)
DEI_SEVERE: float = 0.5
DEI_MODERATE: float = 0.15

# Overconfidence Score (OCS)
OCS_SEVERE: float = 0.7
OCS_MODERATE: float = 0.4

# Loss Aversion Index (LAI)
LAI_SEVERE: float = 2.0
LAI_MODERATE: float = 1.5

# ---------------------------------------------------------------------------
# Stock catalog
# ---------------------------------------------------------------------------
STOCK_CATALOG_FILE = DATA_DIR / "stock_catalog.json"
MARKET_SNAPSHOTS_FILE = DATA_DIR / "all_market_snapshots.csv"

# Volatility classes considered "high risk"
HIGH_VOLATILITY_CLASSES = {"high"}
