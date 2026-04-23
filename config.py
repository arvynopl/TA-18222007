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
SURVEY_PRIOR_WEIGHT: float = 0.15  # Damping factor for survey-informed CDT priors
CDT_STABILITY_WINDOW: int = 5  # Number of past sessions used for stability index

# Adaptive alpha bounds for EMA (activity-weighted update rate)
# Low-activity sessions use ALPHA; fully-active sessions use ALPHA_MAX.
ALPHA_MAX: float = 0.45  # Upper bound for high-activity sessions (buy+sell fills all rounds)

# CDT state snapshot & feedback
LAI_EMA_CEILING: float = 3.0   # LAI is normalised as min(LAI/LAI_EMA_CEILING, 1) before EMA
CDT_MODIFIER_STABILITY_THRESHOLD: float = 0.75  # Stability above this triggers pattern-persistence modifier

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

# Minimum realized trades required before DEI/LAI severity can exceed "mild"
# Sessions with fewer than this many realized round-trips are capped at "mild"
MIN_TRADES_FOR_FULL_SEVERITY: int = 3

# ---------------------------------------------------------------------------
# DEI formula variant selection
# ---------------------------------------------------------------------------
# If True (production default), use dollar-weighted DEI (Frazzini, 2006):
#   weights each position by trade value (quantity × |price_diff|).
# If False, use count-based DEI (Odean, 1998): equal weight per position.
# Both variants produce DEI ∈ [−1, 1]; switch does not affect severity thresholds.
USE_DOLLAR_WEIGHTED_DEI: bool = True

# ---------------------------------------------------------------------------
# Stock catalog
# ---------------------------------------------------------------------------
STOCK_CATALOG_FILE = DATA_DIR / "stock_catalog.json"
MARKET_SNAPSHOTS_FILE = DATA_DIR / "all_market_snapshots.csv"

# Volatility classes considered "high risk"
HIGH_VOLATILITY_CLASSES = {"high"}

# Design note: only "high" volatility stocks contribute to observed_risk
# in update_profile(). Stocks with volatility_class "medium" or below
# count as zero-risk regardless of trading frequency. This is a deliberate
# simplification: risk_preference tracks exposure to the most volatile
# instruments. Future work may extend this to a multi-tier weighting
# (e.g., medium=0.5, high=1.0) for a more granular risk-appetite signal.


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
    if not (0.0 < SURVEY_PRIOR_WEIGHT <= 0.5):
        raise ValueError("SURVEY_PRIOR_WEIGHT must be in (0, 0.5]")

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
    if not (ALPHA < ALPHA_MAX < 1):
        raise ValueError(f"ALPHA_MAX must be in (ALPHA, 1), got ALPHA={ALPHA} ALPHA_MAX={ALPHA_MAX}")
    if LAI_EMA_CEILING <= 0:
        raise ValueError(f"LAI_EMA_CEILING must be > 0, got {LAI_EMA_CEILING}")
    if MIN_TRADES_FOR_FULL_SEVERITY < 1:
        raise ValueError(f"MIN_TRADES_FOR_FULL_SEVERITY must be >= 1, got {MIN_TRADES_FOR_FULL_SEVERITY}")
    if not isinstance(USE_DOLLAR_WEIGHTED_DEI, bool):
        raise ValueError("USE_DOLLAR_WEIGHTED_DEI must be a bool")
