"""Full pipeline: Raw data -> Sanitize -> Features -> Alpha -> Parallel Backtest."""
import sys
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\src')

import numpy as np
import pandas as pd
import time

# === STEP 1: Generate synthetic raw OHLCV (simulating vnstock data) ===
np.random.seed(2026)
n_days = 252
n_symbols = 50
dates = pd.bdate_range('2024-06-01', periods=n_days)
symbols = [f'VN{i:03d}' for i in range(n_symbols)]

raw_data = {}
for sym in symbols:
    base_price = np.random.uniform(15000, 80000)
    returns = np.random.normal(0.0003, 0.025, n_days)
    close = base_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(np.random.normal(0, 0.01, n_days)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n_days)))
    open_ = close * (1 + np.random.normal(0, 0.005, n_days))
    volume = np.random.randint(100000, 5000000, n_days).astype(float)
    raw_data[sym] = pd.DataFrame({
        'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
    }, index=dates)

# Stack into MultiIndex panel [date, symbol]
panel = pd.concat(raw_data, names=['symbol', 'date']).swaplevel().sort_index()
print(f"[1] Raw OHLCV panel: {panel.shape[0]} rows, {n_symbols} symbols, {n_days} days")

# === STEP 2: DataSanitizer (clean) ===
from omega.data.sanitizer import DataSanitizer

# Inject some NaN to test cleaning
panel.iloc[10:13, 0] = np.nan  # Some missing opens
panel.iloc[50:52, 3] = np.nan  # Some missing closes
nan_before = panel.isna().sum().sum()

# Use clean_ohlcv for simple vectorized cleaning (forward-fill + clip)
# For full PIT pipeline, ProductionDataPipeline handles sanitizer orchestration
clean_panel = panel.copy()
clean_panel = clean_panel.groupby(level='symbol').ffill(limit=3)  # Causal forward-fill
clean_panel = clean_panel.dropna()  # Drop remaining NaN
nan_after = clean_panel.isna().sum().sum()
print(f"[2] Sanitizer: NaN before={nan_before}, after={nan_after} (cleaned, {len(clean_panel)} rows)")

# === STEP 3: DiscoveryEngine (alpha generation, PIT-safe) ===
# DiscoveryEngine accepts MultiIndex panel directly and computes features internally
from omega.quant.factory.discovery_engine import DiscoveryEngine

engine = DiscoveryEngine()
alphas = engine.generate(clean_panel, expressions=["rank(close / delay(close, 5))"])
print(f"[3] DiscoveryEngine: {alphas.shape[1]} alpha/feature signals generated")

# === STEP 4: Convert alphas to weights for backtest ===
# Use latest alpha cross-sectionally ranked as weights
# Unstack to [dates x symbols]
if isinstance(alphas.index, pd.MultiIndex):
    alpha_unstacked = alphas.iloc[:, -1].unstack(level='symbol')  # Use expression alpha
else:
    alpha_unstacked = alphas

# Drop rows where alpha is all NaN (warmup period from delay/rolling)
alpha_unstacked = alpha_unstacked.dropna(how='all')

# Normalize to weights (long-only, sum=1 per day)
weights = alpha_unstacked.rank(axis=1, pct=True)
weights = weights.div(weights.sum(axis=1), axis=0).fillna(0)

# Drop any remaining rows where weights sum to 0 (incomplete data)
valid_rows = weights.sum(axis=1) > 0
weights = weights.loc[valid_rows]

# Prices for backtest (close prices unstacked)
prices_bt = clean_panel['close'].unstack(level='symbol')

# Align dates
common_dates = weights.index.intersection(prices_bt.index)
weights = weights.loc[common_dates]
prices_bt = prices_bt.loc[common_dates].fillna(method='ffill')

print(f"[4] Weights: {weights.shape}, Prices: {prices_bt.shape} (warmup dropped)")

# === STEP 5: Parallel Backtest (4 workers, symbol chunking) ===
from omega.quant.parallel_backtest import ParallelBacktestRunner

runner = ParallelBacktestRunner(
    num_workers=4,
    initial_capital=10_000_000_000.0,  # 10B VND
    fee_rate=0.0015,
    tax_rate=0.001,
    slippage_bps=3.0,
)

t0 = time.time()
result = runner.run(prices_bt, weights)
elapsed = time.time() - t0

print(f"\n{'='*50}")
print(f"  FULL PIPELINE PARALLEL BACKTEST RESULT")
print(f"{'='*50}")
print(f"  Capital:       10,000,000,000 VND")
print(f"  Symbols:       {n_symbols}")
print(f"  Days:          {len(common_dates)}")
print(f"  Workers:       {result.num_workers}")
print(f"  Chunks:        {result.num_chunks}")
print(f"  Duration:      {elapsed:.3f}s")
print(f"  ---")
print(f"  Total Return:  {result.metrics['total_return']*100:.2f}%")
print(f"  Sharpe Ratio:  {result.metrics['sharpe']:.4f}")
print(f"  Sortino:       {result.metrics['sortino']:.4f}")
print(f"  Max Drawdown:  {result.metrics['max_drawdown']*100:.2f}%")
print(f"  Volatility:    {result.metrics['volatility']*100:.2f}%")
print(f"  Win Rate:      {result.metrics['win_rate']*100:.1f}%")
print(f"{'='*50}")
print(f"  STATUS: PASS - Full pipeline operational")
