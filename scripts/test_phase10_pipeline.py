#!/usr/bin/env python3
"""
Phase 10 Test Runner - Production Pipeline with market_2015_now.parquet
========================================================================
Test daily rebalance pipeline with full market data (2015-2026).

NO DEPENDENCY ON SKILLS - runs standalone.
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Test configuration
DATA_FILE = PROJECT_ROOT / "data/market_2015_now.parquet"
TEST_DATE = "2026-05-11"  # Last trading day in data
LOOKBACK_DAYS = 252  # 1 year lookback

print("="*70)
print("PHASE 10 TEST - PRODUCTION PIPELINE")
print("="*70)
print(f"Data file: {DATA_FILE}")
print(f"Test date: {TEST_DATE}")
print(f"Lookback: {LOOKBACK_DAYS} days")
print()

# Step 1: Load data
print("[1/5] Loading market data...")
start_time = time.time()

if not DATA_FILE.exists():
    print(f"ERROR: Data file not found: {DATA_FILE}")
    sys.exit(1)

df = pd.read_parquet(DATA_FILE)
df['date'] = pd.to_datetime(df['date'])

load_time = time.time() - start_time
print(f"  Loaded {len(df)} rows, {df['ticker'].nunique()} tickers")
print(f"  Date range: {df['date'].min().date()} to {df['date'].max().date()}")
print(f"  Time: {load_time:.2f}s")
print()

# Step 2: Filter to test window
print("[2/5] Filtering to test window...")
start_time = time.time()

test_date = pd.Timestamp(TEST_DATE)
start_date = test_date - pd.Timedelta(days=LOOKBACK_DAYS)

df_window = df[(df['date'] >= start_date) & (df['date'] <= test_date)].copy()

filter_time = time.time() - start_time
print(f"  Window: {start_date.date()} to {test_date.date()}")
print(f"  Rows: {len(df_window)}")
print(f"  Tickers: {df_window['ticker'].nunique()}")
print(f"  Time: {filter_time:.2f}s")
print()

# Step 3: Compute features (simple momentum + volatility)
print("[3/5] Computing features...")
start_time = time.time()

# Deduplicate then pivot to wide format for vectorized operations
# Some date+ticker pairs can appear multiple times in raw market dump
# Keep last close per date+ticker
if df_window.duplicated(subset=['date', 'ticker']).any():
    dup_count = int(df_window.duplicated(subset=['date', 'ticker']).sum())
    print(f"  Found {dup_count} duplicate date+ticker rows, aggregating with last close")

df_pivot = df_window.pivot_table(index='date', columns='ticker', values='close', aggfunc='last')

# Momentum: 20-day return
returns_20d = df_pivot.pct_change(20)

# Volatility: 20-day rolling std
volatility_20d = df_pivot.pct_change().rolling(20).std()

# Rank signals (higher momentum, lower volatility = better)
momentum_rank = returns_20d.rank(axis=1, ascending=False)
volatility_rank = volatility_20d.rank(axis=1, ascending=True)

# Combined score
signal_score = (momentum_rank + volatility_rank) / 2

# Apply T-1 lag: shift signals forward by 1 day to ensure we use yesterday's signals
signal_score_lagged = signal_score.shift(1)

# Get latest signals (now T-1)
latest_signals = signal_score_lagged.iloc[-1].dropna().sort_values()

feature_time = time.time() - start_time
print(f"  Features computed for {len(latest_signals)} tickers")
print(f"  Top 10 signals: {list(latest_signals.head(10).index)}")
print(f"  Time: {feature_time:.2f}s")
print()

# Step 4: Portfolio construction (top 20, equal weight)
print("[4/5] Constructing portfolio...")
start_time = time.time()

TOP_N = 20
top_tickers = latest_signals.head(TOP_N).index.tolist()
weights = pd.Series(1.0 / TOP_N, index=top_tickers)

portfolio_time = time.time() - start_time
print(f"  Portfolio: {TOP_N} positions, equal weight")
print(f"  Tickers: {top_tickers[:10]}...")
print(f"  Time: {portfolio_time:.2f}s")
print()

# Step 5: Risk checks (simple position size check)
print("[5/5] Risk checks...")
start_time = time.time()

MAX_POSITION_SIZE = 0.10  # 10% max per position
violations = weights[weights > MAX_POSITION_SIZE]

if len(violations) > 0:
    print(f"  RISK VIOLATION: {len(violations)} positions exceed {MAX_POSITION_SIZE*100}%")
    risk_passed = False
else:
    print(f"  Risk checks PASSED")
    risk_passed = True

risk_time = time.time() - start_time
print(f"  Time: {risk_time:.2f}s")
print()

# Summary
print("="*70)
print("PHASE 10 TEST SUMMARY")
print("="*70)

total_time = load_time + filter_time + feature_time + portfolio_time + risk_time

print(f"Total pipeline time: {total_time:.2f}s")
print(f"  Load data:       {load_time:.2f}s ({load_time/total_time*100:.1f}%)")
print(f"  Filter window:   {filter_time:.2f}s ({filter_time/total_time*100:.1f}%)")
print(f"  Compute features:{feature_time:.2f}s ({feature_time/total_time*100:.1f}%)")
print(f"  Portfolio:       {portfolio_time:.2f}s ({portfolio_time/total_time*100:.1f}%)")
print(f"  Risk checks:     {risk_time:.2f}s ({risk_time/total_time*100:.1f}%)")
print()

# Performance target
TARGET_TIME = 10.0
if total_time < TARGET_TIME:
    print(f"PASS: Pipeline < {TARGET_TIME}s target")
    exit_code = 0
else:
    print(f"FAIL: Pipeline {total_time:.2f}s > {TARGET_TIME}s target")
    exit_code = 1

print(f"Risk checks: {'PASS' if risk_passed else 'FAIL'}")
print()

if __name__ == "__main__":
    sys.exit(exit_code)
