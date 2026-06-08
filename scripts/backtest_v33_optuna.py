"""
OMEGA_QUANT Backtest v3.3 - Optuna Optimized vs Fixed Params
Tune on TRAIN, validate on VAL, backtest on TEST. Compare with v3.1 fixed.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 3.3
"""
import sys
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

import numpy as np
import pandas as pd
import logging
import time
import json
from pathlib import Path
from datetime import datetime
from scipy import stats

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from omega.quant.evolution.optuna_param_tuner import OptunaParamTuner
from omega.quant.evolution.regime_detector import RegimeDetector, RegimeConfig
from omega.quant.evolution.hrp_weighter import HRPWeighter
from omega.quant.evolution.ml_alpha_integration import MLAlphaIntegration
from omega.quant.parallel_backtest import ParallelBacktestRunner

# ============================================================
# DATA
# ============================================================
logger.info("=" * 70)
logger.info("BACKTEST v3.3 - OPTUNA OPTIMIZED PARAMS")
logger.info("=" * 70)

df = pd.read_parquet(str(Path(__file__).resolve().parents[1] / 'data' / 'market_2015_now.parquet'))
df['date'] = pd.to_datetime(df['date'])
ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
df[ohlcv_cols] = df.groupby('ticker')[ohlcv_cols].ffill(limit=3)
df = df.dropna(subset=['close', 'volume'])
df = df[(df['close'] > 0) & (df['volume'] > 0)]
df['adv_60'] = df.groupby('ticker')['volume'].transform(lambda x: x.rolling(60, min_periods=20).mean())
df = df.dropna(subset=['adv_60'])

TRAIN_END = pd.Timestamp('2022-06-30')
VAL_START = pd.Timestamp('2022-08-01')
VAL_END = pd.Timestamp('2024-06-30')
TEST_START = pd.Timestamp('2024-08-01')

train_df = df[df['date'] <= TRAIN_END].copy()
val_df = df[(df['date'] >= VAL_START) & (df['date'] <= VAL_END)].copy()
test_df = df[df['date'] >= TEST_START].copy()

def get_pit_universe(period_df, top_n=50):
    last_date = period_df['date'].max()
    recent = period_df[period_df['date'] >= last_date - pd.Timedelta(days=90)]
    return recent.groupby('ticker')['adv_60'].mean().sort_values(ascending=False).head(top_n).index.tolist()

train_df = train_df[train_df['ticker'].isin(get_pit_universe(train_df))]
val_df = val_df[val_df['ticker'].isin(get_pit_universe(val_df))]
test_df = test_df[test_df['ticker'].isin(get_pit_universe(test_df))]

def build_panel(period_df):
    panel = period_df.set_index(['date', 'ticker'])[ohlcv_cols].sort_index()
    panel.index.names = ['date', 'symbol']
    panel['returns'] = panel.groupby(level='symbol')['close'].pct_change()
    return panel.dropna(subset=['returns'])

train_panel = build_panel(train_df)
val_panel = build_panel(val_df)
test_panel = build_panel(test_df)

# Generate features on TRAIN for Optuna
logger.info("Generating features on TRAIN for Optuna...")
adapter = UnifiedFeatureAdapter(use_arsenal=True, use_alt_features=True, use_alt_data=True)
train_featured = adapter.generate_all(train_panel)
features = adapter.get_all_feature_names()
logger.info("TRAIN features: %d (%d rows)", len(features), len(train_featured))

# ============================================================
# PHASE 1: OPTUNA TUNING (on TRAIN only)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE 1: OPTUNA TUNING (30 trials on TRAIN)")
logger.info("=" * 70)

tuner = OptunaParamTuner(n_trials=30, n_jobs=1)
t0 = time.time()
best_params = tuner.tune(train_featured, features)
tune_time = time.time() - t0
logger.info("Optuna done in %.1fs. Best Sharpe on TRAIN: %.4f", tune_time, best_params.objective_value)

# ============================================================
# PHASE 2: BACKTEST WITH OPTIMIZED PARAMS (on TEST)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE 2: BACKTEST WITH OPTIMIZED PARAMS")
logger.info("=" * 70)

# Generate features on VAL + TEST
val_featured = adapter.generate_all(val_panel)
test_featured = adapter.generate_all(test_panel)

# Screen on VAL with optimized corr_threshold and n_signals
target_col = 'fwd_ret_5'
val_h = val_featured.copy()
val_h[target_col] = val_h.groupby(level='symbol')['close'].pct_change(5).shift(-5)
val_h = val_h.dropna(subset=[target_col])

screened = []
for feat in features:
    if feat not in val_h.columns:
        continue
    try:
        sig = val_h[feat].groupby(level='symbol').shift(1)
        if sig.std() < 1e-8:
            continue
        ic = sig.corr(val_h[target_col], method='spearman')
        if not np.isnan(ic) and abs(ic) >= 0.03:
            screened.append({'feature': feat, 'ic': float(ic), 'abs_ic': abs(float(ic))})
    except Exception:
        continue
screened.sort(key=lambda x: x['abs_ic'], reverse=True)

# Orthogonality with OPTIMIZED corr_threshold
accepted = []
accepted_sigs = {}
for sa in screened:
    feat = sa['feature']
    try:
        sig = val_h[feat].groupby(level='symbol').shift(1)
        if sig.std() < 1e-8:
            continue
        is_diverse = True
        for _, esig in accepted_sigs.items():
            common = sig.index.intersection(esig.index)
            if len(common) > 100 and abs(sig.loc[common].corr(esig.loc[common])) > best_params.corr_threshold:
                is_diverse = False
                break
        if is_diverse:
            accepted.append(sa)
            accepted_sigs[feat] = sig
            if len(accepted) >= best_params.n_signals:
                break
    except Exception:
        continue

logger.info("Optimized screening: %d signals (corr<%.2f, n=%d)",
            len(accepted), best_params.corr_threshold, best_params.n_signals)

# Train ML with OPTIMIZED Ridge alpha
from sklearn.linear_model import Ridge
train_h = val_h.copy()  # Train ML on VAL (same as v3.1)
feat_names = [a['feature'] for a in accepted if a['feature'] in train_h.columns]
X = train_h[feat_names].replace([np.inf, -np.inf], np.nan).fillna(0)
y = train_h[target_col].replace([np.inf, -np.inf], np.nan).fillna(0)
model = Ridge(alpha=best_params.ridge_alpha)
model.fit(X.values, y.values)
train_ic = pd.Series(model.predict(X.values)).corr(y.reset_index(drop=True), method='spearman')
logger.info("ML trained: Ridge(alpha=%.3f), IC=%.4f", best_params.ridge_alpha, train_ic)

# Predict on TEST
test_X = test_featured[feat_names].replace([np.inf, -np.inf], np.nan).fillna(0)
test_preds = model.predict(test_X.values)
ml_signal = pd.Series(test_preds, index=test_featured.index).groupby(level='symbol').shift(1).fillna(0)

# Build weights from ML signal
test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()
ml_unstacked = ml_signal.unstack(level='symbol')
if isinstance(ml_unstacked, pd.DataFrame):
    ranked = ml_unstacked.rank(axis=1, pct=True)
    weights = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)
else:
    weights = pd.DataFrame(1.0/len(test_prices.columns), index=test_prices.index, columns=test_prices.columns)

# Regime with OPTIMIZED MA params
regime_config = RegimeConfig(ma_short=best_params.regime_ma_short, ma_long=best_params.regime_ma_long)
regime_det = RegimeDetector(config=regime_config)
full_market = df.groupby('date')['close'].mean()
regime_df = regime_det.detect_rolling(full_market)
weights = regime_det.adjust_weights(weights, regime_df)

# Constraints (fixed - not tuned)
weights = weights.clip(upper=0.05)
row_sums = weights.sum(axis=1).replace(0, 1.0)
weights = weights.div(row_sums, axis=0)

BOARD_LOT, CAPITAL = 100, 10_000_000_000.0
for i in range(len(weights)):
    for col in weights.columns:
        w = weights.iloc[i][col]
        if w > 0 and col in test_prices.columns:
            price = test_prices.iloc[min(i, len(test_prices)-1)][col]
            if price > 0:
                shares = int((w * CAPITAL) / price / BOARD_LOT) * BOARD_LOT
                weights.iloc[i, weights.columns.get_loc(col)] = (shares * price) / CAPITAL
    rs = weights.iloc[i].sum()
    if rs > 0:
        weights.iloc[i] = weights.iloc[i] / rs

DAILY_TURNOVER_CAP = 0.0119
for i in range(1, len(weights)):
    change = (weights.iloc[i] - weights.iloc[i-1]).abs().sum()
    if change > DAILY_TURNOVER_CAP:
        scale = DAILY_TURNOVER_CAP / change
        weights.iloc[i] = weights.iloc[i-1] + (weights.iloc[i] - weights.iloc[i-1]) * scale
        rs = weights.iloc[i].sum()
        if rs > 0:
            weights.iloc[i] = weights.iloc[i] / rs

valid = weights.sum(axis=1) > 0
weights = weights.loc[valid]
test_prices_aligned = test_prices.loc[weights.index]
common_cols = weights.columns.intersection(test_prices_aligned.columns)
weights = weights[common_cols]
test_prices_aligned = test_prices_aligned[common_cols]

# Slippage
test_adv = test_df.groupby('ticker')['adv_60'].mean().sort_values(ascending=False)
top30 = test_adv.head(30).index.tolist()
top30_w = weights[[c for c in common_cols if c in top30]].sum(axis=1).mean()
avg_slippage = 5.0 * top30_w + 10.0 * (1 - top30_w)

# Backtest
runner = ParallelBacktestRunner(num_workers=4, initial_capital=CAPITAL, fee_rate=0.0015, tax_rate=0.001, slippage_bps=avg_slippage)
t1 = time.time()
bt_result = runner.run(test_prices_aligned, weights)
bt_time = time.time() - t1

# Walk-forward
wf_results = []
cs = test_prices_aligned.index[0]
ed = test_prices_aligned.index[-1]
while cs + pd.DateOffset(months=12) <= ed + pd.DateOffset(days=30):
    we = cs + pd.DateOffset(months=12)
    mask = (test_prices_aligned.index >= cs) & (test_prices_aligned.index < we)
    wp, ww = test_prices_aligned.loc[mask], weights.loc[mask]
    if len(wp) >= 20:
        try:
            wr = ParallelBacktestRunner(num_workers=2, initial_capital=CAPITAL, fee_rate=0.0015, tax_rate=0.001, slippage_bps=avg_slippage)
            wb = wr.run(wp, ww)
            wf_results.append({"start": str(cs.date()), "end": str(we.date()), "return": float(wb.metrics['total_return']), "sharpe": float(wb.metrics['sharpe'])})
        except Exception:
            pass
    cs += pd.DateOffset(months=6)

# ============================================================
# PHASE 3: REPORT + COMPARISON
# ============================================================
metrics = bt_result.metrics
calmar = (bt_result.returns.mean() * 252) / abs(metrics['max_drawdown']) if metrics['max_drawdown'] != 0 else 0
avg_turnover = weights.diff().abs().sum(axis=1).mean()

print()
print("=" * 70)
print("  OMEGA_QUANT BACKTEST v3.3 - OPTUNA OPTIMIZED")
print("=" * 70)
print(f"  OPTIMIZED PARAMS (from {best_params.n_trials} Optuna trials on TRAIN):")
print(f"    Ridge alpha:     {best_params.ridge_alpha:.4f}")
print(f"    HRP lookback:    {best_params.hrp_lookback} days")
print(f"    Corr threshold:  {best_params.corr_threshold:.2f}")
print(f"    Regime MA:       {best_params.regime_ma_short}/{best_params.regime_ma_long}")
print(f"    N signals:       {best_params.n_signals}")
print(f"    Train Sharpe:    {best_params.objective_value:.4f}")
print(f"  ---")
print(f"  Period:          {test_prices_aligned.index[0].date()} to {test_prices_aligned.index[-1].date()}")
print(f"  Capital:         10B VND | Symbols: {len(common_cols)}")
print(f"  Signals:         {len(accepted)}")
print(f"  ML Train IC:     {train_ic:.4f}")
print(f"  ---")
print(f"  Total Return:    {metrics['total_return']*100:.2f}%")
print(f"  Sharpe Ratio:    {metrics['sharpe']:.4f}")
print(f"  Sortino Ratio:   {metrics['sortino']:.4f}")
print(f"  Calmar Ratio:    {calmar:.4f}")
print(f"  Max Drawdown:    {metrics['max_drawdown']*100:.2f}%")
print(f"  Volatility:      {metrics['volatility']*100:.2f}%")
print(f"  Win Rate:        {metrics['win_rate']*100:.1f}%")
print(f"  Avg Turnover:    {avg_turnover*100:.2f}%/day")
if wf_results:
    print(f"  WF Avg Sharpe:   {np.mean([w['sharpe'] for w in wf_results]):.4f}")
print(f"  ---")
print(f"  Tune Time:       {tune_time:.1f}s | Backtest: {bt_time:.1f}s")
print("=" * 70)
print()
print("  COMPARISON: FIXED vs OPTUNA")
print("  " + "-" * 60)
print("  v3.1 (FIXED):  corr=0.50, n=20, ridge=1.0, MA=50/200")
print("  v3.1 RESULT:   Sharpe 1.11 | Return +51% | WF 1.67")
print("  " + "-" * 60)
print(f"  v3.3 (OPTUNA): corr={best_params.corr_threshold:.2f}, n={best_params.n_signals}, ridge={best_params.ridge_alpha:.3f}, MA={best_params.regime_ma_short}/{best_params.regime_ma_long}")
print(f"  v3.3 RESULT:   Sharpe {metrics['sharpe']:.2f} | Return {metrics['total_return']*100:.0f}% | WF {np.mean([w['sharpe'] for w in wf_results]):.2f}" if wf_results else f"  v3.3 RESULT:   Sharpe {metrics['sharpe']:.2f} | Return {metrics['total_return']*100:.0f}%")
print("  " + "-" * 60)
delta_sharpe = metrics['sharpe'] - 1.11
print(f"  DELTA:         Sharpe {delta_sharpe:+.2f} | {'IMPROVED' if delta_sharpe > 0 else 'NO IMPROVEMENT'}")
print()

# Save
results_dir = Path('data/backtest_v33_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "version": "3.3", "timestamp": datetime.utcnow().isoformat(),
    "strategy": "optuna_optimized",
    "optuna": {
        "n_trials": best_params.n_trials,
        "train_sharpe": best_params.objective_value,
        "params": {
            "ridge_alpha": best_params.ridge_alpha,
            "hrp_lookback": best_params.hrp_lookback,
            "corr_threshold": best_params.corr_threshold,
            "regime_ma_short": best_params.regime_ma_short,
            "regime_ma_long": best_params.regime_ma_long,
            "n_signals": best_params.n_signals,
        },
    },
    "comparison": {
        "v31_fixed": {"sharpe": 1.11, "return": 0.51, "wf_sharpe": 1.67},
        "v33_optuna": {"sharpe": float(metrics['sharpe']), "return": float(metrics['total_return']),
                       "wf_sharpe": float(np.mean([w['sharpe'] for w in wf_results])) if wf_results else 0},
    },
    "metrics": {k: float(v) for k, v in metrics.items()},
    "walk_forward": wf_results,
}
with open(results_dir / 'backtest_v33_results.json', 'w') as f:
    json.dump(summary, f, indent=2, default=str)
bt_result.equity_curve.to_csv(results_dir / 'equity_curve.csv')
logger.info("Saved to data/backtest_v33_results/")
logger.info("BACKTEST v3.3 COMPLETE")
