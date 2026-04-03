"""
IDX Stock Data Acquisition Script
==================================
Downloads 2 years of historical OHLCV data for 6 IDX-listed stocks,
computes technical indicators (MA_5, MA_20, RSI_14), and exports
to CSV files ready for database seeding.

Thesis: CDT-Based Behavioral Bias Detection System
Author: Arvyno Pranata Limahardja (18222007)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import json
import sys

STOCK_CATALOG = {
    "BBCA.JK": {"name": "Bank Central Asia Tbk.", "sector": "Finance", "volatility_class": "low", "bias_role": "Blue-chip anchor — tests disposition effect"},
    "TLKM.JK": {"name": "Telkom Indonesia Tbk.", "sector": "Telecom", "volatility_class": "low_medium", "bias_role": "Stable dividend stock — rational baseline"},
    "ANTM.JK": {"name": "Aneka Tambang Tbk.", "sector": "Mining", "volatility_class": "high", "bias_role": "Commodity volatility — triggers loss aversion & overconfidence"},
    "GOTO.JK": {"name": "GoTo Gojek Tokopedia Tbk.", "sector": "Technology", "volatility_class": "high", "bias_role": "High-sentiment — elicits overtrading & emotional decisions"},
    "UNVR.JK": {"name": "Unilever Indonesia Tbk.", "sector": "Consumer", "volatility_class": "medium", "bias_role": "Defensive with decline periods — tests holding losers"},
    "BBRI.JK": {"name": "Bank Rakyat Indonesia Tbk.", "sector": "Finance", "volatility_class": "medium", "bias_role": "Widely held retail stock — familiar to pilot users"},
}

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def download_stock_data(output_dir="./data"):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)

    print(f"{'='*60}")
    print(f"IDX Data Acquisition: {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}")
    print(f"{'='*60}")

    all_snapshots = []
    catalog_records = []

    for ticker, meta in STOCK_CATALOG.items():
        print(f"\n[{ticker}] Downloading {meta['name']}...")
        try:
            df = yf.Ticker(ticker).history(start=start_date, end=end_date, interval="1d")
            if df.empty:
                print(f"  WARNING: No data for {ticker}. Skipping.")
                continue

            df = df.reset_index()
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)

            df['ticker'] = ticker.replace('.JK', '')
            df['stock_id'] = ticker
            df['ma_5'] = df['close'].rolling(5).mean().round(2)
            df['ma_20'] = df['close'].rolling(20).mean().round(2)
            df['rsi_14'] = compute_rsi(df['close'], 14).round(2)
            df['volatility_20d'] = (np.log(df['close']/df['close'].shift(1)).rolling(20).std() * np.sqrt(252)).round(4)
            df['trend'] = np.where(df['ma_5'] > df['ma_20'], 'bullish', np.where(df['ma_5'] < df['ma_20'], 'bearish', 'neutral'))
            df['daily_return'] = df['close'].pct_change().round(6)

            cols = ['date','stock_id','ticker','open','high','low','close','volume','ma_5','ma_20','rsi_14','volatility_20d','trend','daily_return']
            df_out = df[[c for c in cols if c in df.columns]].copy()

            stock_file = output_path / f"{ticker.replace('.JK','')}_historical.csv"
            df_out.to_csv(stock_file, index=False)
            print(f"  Saved {len(df_out)} records -> {stock_file}")

            all_snapshots.append(df_out)
            catalog_records.append({
                "stock_id": ticker, "ticker": ticker.replace('.JK',''),
                "name": meta["name"], "sector": meta["sector"],
                "volatility_class": meta["volatility_class"], "bias_role": meta["bias_role"],
                "data_start": str(df_out['date'].min().date()),
                "data_end": str(df_out['date'].max().date()),
                "total_records": len(df_out),
                "avg_close": round(df_out['close'].mean(), 2),
                "avg_volume": int(df_out['volume'].mean()),
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    if all_snapshots:
        combined = pd.concat(all_snapshots, ignore_index=True)
        combined.to_csv(output_path / "all_market_snapshots.csv", index=False)
        print(f"\nCombined: {len(combined)} total records saved.")

    with open(output_path / "stock_catalog.json", 'w') as f:
        json.dump(catalog_records, f, indent=2)

    print(f"\n{'='*60}")
    print("SIMULATION WINDOWS (for bias elicitation scenarios)")
    print(f"{'='*60}")
    if all_snapshots:
        combined = pd.concat(all_snapshots, ignore_index=True)
        for rec in catalog_records:
            sd = combined[combined['ticker']==rec['ticker']].sort_values('date').copy()
            if len(sd) < 30: continue
            sd['ret_14d'] = sd['close'].pct_change(14)
            worst = sd.nsmallest(1,'ret_14d')
            best = sd.nlargest(1,'ret_14d')
            if not worst.empty:
                print(f"  [{rec['ticker']}] Crash: {worst.iloc[0]['date']:%Y-%m-%d} ({worst.iloc[0]['ret_14d']:.1%})")
            if not best.empty:
                print(f"  [{rec['ticker']}] Rally: {best.iloc[0]['date']:%Y-%m-%d} ({best.iloc[0]['ret_14d']:+.1%})")

    print(f"\nOutput: {output_path.resolve()}")
    print("Ready for database seeding.")

if __name__ == "__main__":
    download_stock_data(sys.argv[1] if len(sys.argv) > 1 else "./data")
