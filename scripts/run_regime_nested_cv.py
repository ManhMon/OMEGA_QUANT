"""
Run Optuna Nested CV for regime params, compare with manual mild config.
"""
import sys
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\quant\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\core\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\infra\src')

import numpy as np
import pandas as pd
import logging
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from omega.quant.evolution.optuna_regime_nested_cv import OptunaRegimeNestedCV

# Load data
df = pd.read_parquet(r'C:\Users\GHC\.openclaw\workspace\data\market_2015_now.parquet')
df['date'] = pd.to_datetime(df['date'])
ohlcv = ['open', 'high', 'low', 'close', 'volume']
df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
df[ohlcv] = df.groupby('ticker')[ohlcv].ffill(limit=3)
df = df.dropna(subset=['close', 'volume'])
df = df[(df['close'] > 0) & (df['volume'] > 0)]

# Use 2020-2024 period (same as CPCV pipeline)
df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2024-12-31')]
top50 = df.groupby('ticker')['volume'].mean().sort_values(ascending=False).head(50).index.tolist()
df = df[df['ticker'].isin(top50)]

# Build returns matrix (T x N)
pivot_close = df.pivot_table(index='date', columns='ticker', values='close').ffill()
returns = pivot_close.pct_change().fillna(0).values

# Simple equal-weight as proxy (actual weights come from Ridge, but for regime tuning
# we only need the exposure scaling effect on portfolio returns)
N = returns.shape[1]
weights = np.ones_like(returns) / N

# Market returns (equal-weight)
market_returns = returns.mean(axis=1)

logger.info("Data: T=%d, N=%d, period=%s to %s",
            returns.shape[0], returns.shape[1],
            pivot_close.index[0].date(), pivot_close.index[-1].date())

# Run nested CV
tuner = OptunaRegimeNestedCV(n_outer_folds=3, n_inner_trials=20)
result = tuner.tune(returns, weights, market_returns)

# Compare with manual mild config
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\quant\src\omega\quant\portfolio')
from regime_overlay import compute_regime_exposure

mild_exposures = compute_regime_exposure(market_returns, dd_threshold=-0.12, hysteresis_days=10)
mild_final = np.where(mild_exposures > 1.0, 1.05,
             np.where(mild_exposures < 0.6, 0.7, 0.9))
mild_port_ret = (returns * weights).sum(axis=1) * mild_final
mild_sharpe = (mild_port_ret.mean() / mild_port_ret.std()) * np.sqrt(252)

# No regime baseline
no_regime_port_ret = (returns * weights).sum(axis=1)
no_regime_sharpe = (no_regime_port_ret.mean() / no_regime_port_ret.std()) * np.sqrt(252)

# Optuna nested CV result
optuna_exposures = compute_regime_exposure(market_returns, dd_threshold=result.dd_threshold, hysteresis_days=result.hysteresis)
optuna_final = np.where(optuna_exposures > 1.0, result.bull_exposure,
               np.where(optuna_exposures < 0.6, result.bear_exposure, result.sideways_exposure))
optuna_port_ret = (returns * weights).sum(axis=1) * optuna_final
optuna_sharpe = (optuna_port_ret.mean() / optuna_port_ret.std()) * np.sqrt(252)

print()
print("=" * 70)
print("  REGIME PARAMS: MANUAL vs OPTUNA NESTED CV")
print("=" * 70)
print(f"  {'Config':<30} {'Sharpe':>8} {'Params'}")
print(f"  {'-'*30} {'-'*8} {'-'*40}")
print(f"  {'No regime':<30} {no_regime_sharpe:>8.4f}")
print(f"  {'Manual mild':<30} {mild_sharpe:>8.4f} dd=-0.12, hyst=10, bear=0.7, bull=1.05, side=0.9")
print(f"  {'Optuna nested CV':<30} {optuna_sharpe:>8.4f} dd={result.dd_threshold:.3f}, hyst={result.hysteresis}, bear={result.bear_exposure:.2f}, bull={result.bull_exposure:.2f}, side={result.sideways_exposure:.2f}")
print(f"  {'-'*30} {'-'*8} {'-'*40}")
print(f"  Nested CV outer Sharpe: {result.outer_sharpe:.4f} (unbiased estimate)")
print(f"  Nested CV folds: {result.n_outer_folds}")
print("=" * 70)

delta = optuna_sharpe - mild_sharpe
print(f"\n  DELTA (Optuna vs Mild): {delta:+.4f} Sharpe")
if delta > 0.05:
    print("  RECOMMENDATION: Use Optuna params (meaningful improvement)")
elif delta > -0.05:
    print("  RECOMMENDATION: Marginal difference, either config acceptable")
else:
    print("  RECOMMENDATION: Keep manual mild (Optuna no better)")

# Save
results_dir = Path('data/regime_nested_cv_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "no_regime_sharpe": float(no_regime_sharpe),
    "manual_mild_sharpe": float(mild_sharpe),
    "optuna_nested_sharpe": float(optuna_sharpe),
    "optuna_outer_sharpe": float(result.outer_sharpe),
    "optuna_params": {
        "dd_threshold": result.dd_threshold,
        "hysteresis": result.hysteresis,
        "bear_exposure": result.bear_exposure,
        "bull_exposure": result.bull_exposure,
        "sideways_exposure": result.sideways_exposure,
    },
    "manual_params": {
        "dd_threshold": -0.12,
        "hysteresis": 10,
        "bear_exposure": 0.7,
        "bull_exposure": 1.05,
        "sideways_exposure": 0.9,
    },
}
with open(results_dir / 'nested_cv_comparison.json', 'w') as f:
    json.dump(summary, f, indent=2)
logger.info("Saved to data/regime_nested_cv_results/")
