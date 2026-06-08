"""Run Alpha Self-Evolution Pipeline demo."""
import sys
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

import numpy as np
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from omega.quant.evolution.alpha_evolution_pipeline import AlphaEvolutionPipeline, EvolutionConfig

# Generate synthetic market data
np.random.seed(2026)
n_days, n_symbols = 500, 30
dates = pd.bdate_range('2023-01-01', periods=n_days)
symbols = [f'VN{i:03d}' for i in range(n_symbols)]

rows = []
for sym in symbols:
    base = np.random.uniform(20000, 60000)
    rets = np.random.normal(0.0003, 0.02, n_days)
    close = base * np.cumprod(1 + rets)
    high = close * (1 + np.abs(np.random.normal(0, 0.01, n_days)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n_days)))
    opn = close * (1 + np.random.normal(0, 0.005, n_days))
    vol = np.random.randint(100000, 3000000, n_days).astype(float)
    df = pd.DataFrame({'open': opn, 'high': high, 'low': low, 'close': close, 'volume': vol}, index=dates)
    df['symbol'] = sym
    df['date'] = dates
    rows.append(df)

panel = pd.concat(rows).set_index(['date', 'symbol']).sort_index()

# Add forward returns (target)
panel['returns'] = panel.groupby(level='symbol')['close'].pct_change()
panel['fwd_ret_5'] = panel.groupby(level='symbol')['close'].pct_change(5).shift(-5)
panel = panel.dropna()

# Train/test split (70/30 chronological)
all_dates = panel.index.get_level_values('date').unique().sort_values()
split = int(len(all_dates) * 0.7)
train_dates = all_dates[:split]
test_dates = all_dates[split:]

train_df = panel.loc[panel.index.get_level_values('date').isin(train_dates)]
test_df = panel.loc[panel.index.get_level_values('date').isin(test_dates)]

# Prices for backtest
prices = panel['close'].unstack(level='symbol')
prices = prices.loc[test_dates].dropna(axis=1)

print(f'Train: {len(train_df)} rows, Test: {len(test_df)} rows')
print(f'Prices for backtest: {prices.shape}')

# Run evolution (small config for demo)
config = EvolutionConfig(
    population_size=50,
    generations=5,
    max_depth=3,
    ic_threshold=0.02,
    min_hit_rate=0.50,
    backtest_workers=2,
    state_dir='data/alpha_evolution_demo',
)

pipeline = AlphaEvolutionPipeline(config=config)
result = pipeline.run(train_df, test_df, target_col='fwd_ret_5', prices=prices)

print()
print('=' * 60)
print('  ALPHA SELF-EVOLUTION RESULT')
print('=' * 60)
print(f'  Generations:       {result["generations"]}')
print(f'  Total evaluated:   {result["total_evaluated"]}')
print(f'  Quality passed:    {result["quality_passed"]}')
print(f'  Orthogonal passed: {result["orthogonal_passed"]}')
print(f'  Newly promoted:    {result["newly_promoted"]}')
print(f'  Total active:      {result["total_active"]}')
print(f'  Duration:          {result["duration_s"]:.2f}s')
if result['backtest_metrics']:
    bm = result['backtest_metrics']
    print(f'  ---')
    print(f'  Portfolio Sharpe:  {bm.get("sharpe", 0):.4f}')
    print(f'  Portfolio Return:  {bm.get("total_return", 0)*100:.2f}%')
    print(f'  Max Drawdown:      {bm.get("max_drawdown", 0)*100:.2f}%')
print('=' * 60)
