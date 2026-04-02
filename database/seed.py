"""
database/seed.py — Populate StockCatalog and MarketSnapshot from data files.

Functions:
    seed_stock_catalog(session)     — Insert 6 IDX stocks from stock_catalog.json
    seed_market_snapshots(session)  — Insert 2826 rows from all_market_snapshots.csv
    run_seed()                      — Convenience wrapper (creates session + calls both)
"""

import json
import math
from datetime import date

import pandas as pd

from config import MARKET_SNAPSHOTS_FILE, STOCK_CATALOG_FILE
from database.connection import get_session, init_db
from database.models import MarketSnapshot, StockCatalog


def seed_stock_catalog(session) -> int:
    """Seed StockCatalog from stock_catalog.json.

    Skips any stock_id that already exists (idempotent).

    Returns:
        Number of rows inserted.
    """
    with open(STOCK_CATALOG_FILE, "r", encoding="utf-8") as fh:
        catalog = json.load(fh)

    inserted = 0
    for item in catalog:
        existing = (
            session.query(StockCatalog)
            .filter_by(stock_id=item["stock_id"])
            .first()
        )
        if existing:
            continue

        stock = StockCatalog(
            stock_id=item["stock_id"],
            ticker=item["ticker"],
            name=item["name"],
            sector=item["sector"],
            volatility_class=item["volatility_class"],
            bias_role=item.get("bias_role"),
        )
        session.add(stock)
        inserted += 1

    session.flush()
    return inserted


def _safe_float(value) -> float | None:
    """Convert a value to float, returning None for NaN / empty strings."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def seed_market_snapshots(session) -> int:
    """Seed MarketSnapshot from all_market_snapshots.csv.

    Skips rows where (stock_id, date) already exist (idempotent).

    Returns:
        Number of rows inserted.
    """
    df = pd.read_csv(MARKET_SNAPSHOTS_FILE)

    # Collect existing (stock_id, date) pairs to skip duplicates
    existing_pairs = set(
        session.query(MarketSnapshot.stock_id, MarketSnapshot.date).all()
    )

    inserted = 0
    for _, row in df.iterrows():
        row_date = date.fromisoformat(str(row["date"]))
        key = (row["stock_id"], row_date)
        if key in existing_pairs:
            continue

        snapshot = MarketSnapshot(
            stock_id=row["stock_id"],
            date=row_date,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
            ma_5=_safe_float(row.get("ma_5")),
            ma_20=_safe_float(row.get("ma_20")),
            rsi_14=_safe_float(row.get("rsi_14")),
            volatility_20d=_safe_float(row.get("volatility_20d")),
            trend=str(row["trend"]) if pd.notna(row.get("trend")) else None,
            daily_return=_safe_float(row.get("daily_return")),
        )
        session.add(snapshot)
        existing_pairs.add(key)
        inserted += 1

        # Flush in batches to avoid large memory spikes
        if inserted % 500 == 0:
            session.flush()

    session.flush()
    return inserted


def run_seed() -> None:
    """Initialize DB schema and seed reference data from CSV/JSON files."""
    init_db()
    with get_session() as sess:
        catalog_count = seed_stock_catalog(sess)
        snapshot_count = seed_market_snapshots(sess)
        print(
            f"Seed complete — {catalog_count} stocks, {snapshot_count} snapshots inserted."
        )


if __name__ == "__main__":
    run_seed()
