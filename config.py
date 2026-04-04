"""
config.py — Central configuration for the CDT Bias Detection System.

All tunable parameters, thresholds, and paths are defined here.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("CDT_DATABASE_URL", f"sqlite:///{BASE_DIR / 'cdt_bias.db'}")

# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------
INITIAL_CAPITAL: float = 10_000_000.0   # Rp 10,000,000
ROUNDS_PER_SESSION: int = 14
PRE_WINDOW_DAYS: int = 30               # Days of history shown before the trading window

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
DEI_MILD: float = 0.05

# Overconfidence Score (OCS)
OCS_SEVERE: float = 0.7
OCS_MODERATE: float = 0.4
OCS_MILD: float = 0.2

# Loss Aversion Index (LAI)
LAI_SEVERE: float = 2.0
LAI_MODERATE: float = 1.5
LAI_MILD: float = 1.2

# ---------------------------------------------------------------------------
# Stock catalog
# ---------------------------------------------------------------------------
STOCK_CATALOG_FILE = DATA_DIR / "stock_catalog.json"
MARKET_SNAPSHOTS_FILE = DATA_DIR / "all_market_snapshots.csv"

# Volatility classes considered "high risk"
HIGH_VOLATILITY_CLASSES = {"high"}


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def validate_config() -> None:
    """Assert that all configuration parameters are internally consistent.

    Raises:
        ValueError: if any parameter violates its constraint.

    Call this once at application startup (e.g. in app.py) to catch
    misconfigured thresholds before they silently corrupt bias scores.
    """
    if INITIAL_CAPITAL <= 0:
        raise ValueError(f"INITIAL_CAPITAL must be > 0, got {INITIAL_CAPITAL}")
    if ROUNDS_PER_SESSION <= 0:
        raise ValueError(f"ROUNDS_PER_SESSION must be > 0, got {ROUNDS_PER_SESSION}")
    if not (0 < ALPHA < 1):
        raise ValueError(f"ALPHA must be in (0, 1), got {ALPHA}")
    if not (0 < BETA < 1):
        raise ValueError(f"BETA must be in (0, 1), got {BETA}")

    # Severity thresholds must be strictly ordered: mild < moderate < severe
    for label, mild, moderate, severe in [
        ("DEI", DEI_MILD, DEI_MODERATE, DEI_SEVERE),
        ("OCS", OCS_MILD, OCS_MODERATE, OCS_SEVERE),
        ("LAI", LAI_MILD, LAI_MODERATE, LAI_SEVERE),
    ]:
        if not (mild < moderate < severe):
            raise ValueError(
                f"{label} thresholds must satisfy mild < moderate < severe, "
                f"got mild={mild} moderate={moderate} severe={severe}"
            )
