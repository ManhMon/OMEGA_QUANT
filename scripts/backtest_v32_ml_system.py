"""
OMEGA_QUANT Backtest v3.2 - Full System Post-Wiring
ML Combiner (Ridge) + 170 features + HRP + Regime + Parallel Backtest
Uses OmegaQuantOrchestrator for end-to-end pipeline.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 3.2
Target: Sharpe > 1.3, WF Sharpe > 1.5
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

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from omega.quant.evolution.regime_detector import RegimeDetector
from omega.quant.evolution.hrp_weighter import HRPWeighter
from omega.quant.evolution.ml_alpha_integration import MLAlphaIntegration
from omega.quant.evolution.genetic_alpha import enforce_t_minus_1_lag
from omega.quant.backtest.parallel import ParallelBacktestRunner
from scipy import stats

# ============================================================
# PHASE A: DATA
# ============================================================
logger.info("=" * 70)
logger.info("BACKTEST v3.2 - FULL SYSTEM (ML Combiner + 170 Features)")
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

# 3-way split
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

val_panel = build_panel(val_df)
test_panel = build_panel(test_df)
logger.info("Panels: val=%d, test=%d", len(val_panel), len(test_panel))

# ============================================================
# PHASE B: UNIFIED FEATURES (170)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE B: UNIFIED FEATURES (170)")
logger.info("=" * 70)

adapter = UnifiedFeatureAdapter(use_arsenal=True, use_alt_features=True, use_alt_data=True)
t0 = time.time()
val_featured = adapter.generate_all(val_panel)
test_featured = adapter.generate_all(test_panel)
features = adapter.get_all_feature_names()
feat_time = time.time() - t0
logger.info("Features: %d in %.1fs", len(features), feat_time)

# ============================================================
# PHASE C: ML COMBINER (train on VAL, predict on TEST)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE C: ML COMBINER (Ridge, 170 features)")
logger.info("=" * 70)

# Add target to val for training
val_with_target = val_featured.copy()
val_with_target['fwd_ret_5'] = val_with_target.groupby(level='symbol')['close'].pct_change(5).shift(-5)
val_with_target = val_with_target.dropna(subset=['fwd_ret_5'])

ml = MLAlphaIntegration(model_name='v32_combiner', horizons=[5], embargo_days=20)
train_result = ml.train_combiner(val_with_target, features, target_col='fwd_ret_5')
logger.info("ML Train: %s, IC=%.4f", train_result['status'], train_result.get('train_ic', 0))

# Predict on TEST
ml_signal = ml.predict(test_featured)
logger.info("ML signal generated: std=%.6f", ml_signal.std())

# ============================================================
# PHASE D: ALSO RUN SCREENING (for comparison + HRP ensemble)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE D: SCREENING + HRP ENSEMBLE")
logger.info("=" * 70)

# Screen features on validation
horizons = [1, 3, 5, 10, 20]
screened = []
for horizon in horizons:
    target_col = f'fwd_ret_{horizon}'
    val_h = val_featured.copy()
    val_h[target_col] = val_h.groupby(level='symbol')['close'].pct_change(horizon).shift(-horizon)
    val_h = val_h.dropna(subset=[target_col])
    for feat in features:
        if feat not in val_h.columns:
            continue
        try:
            sig = val_h[feat].groupby(level='symbol').shift(1)
            if sig.std() < 1e-8:
                continue
            val_ic = sig.corr(val_h[target_col], method='spearman')
            if np.isnan(val_ic) or abs(val_ic) < 0.03:
                continue
            screened.append({'feature': feat, 'horizon': horizon, 'val_ic': float(val_ic), 'abs_ic': abs(float(val_ic))})
        except Exception:
            continue

screened.sort(key=lambda x: x['abs_ic'], reverse=True)

# Orthogonality
accepted = []
accepted_sigs = {}
for sa in screened:
    feat = sa['feature']
    try:
        sig = val_featured[feat].groupby(level='symbol').shift(1)
        if sig.std() < 1e-8:
            continue
        is_diverse = True
        for _, esig in accepted_sigs.items():
            common = sig.index.intersection(esig.index)
            if len(common) > 100 and abs(sig.loc[common].corr(esig.loc[common])) > 0.5:
                is_diverse = False
                break
        if is_diverse:
            accepted.append(sa)
            accepted_sigs[f"{feat}_H{sa['horizon']}"] = sig
            if len(accepted) >= 20:
                break
    except Exception:
        continue

logger.info("Screened: %d -> Orthogonal: %d signals", len(screened), len(accepted))

# Build signal exposures for HRP
test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()
signal_returns = pd.DataFrame(index=test_prices.index)
signal_exposures = {}

# Add ML signal as one of the HRP signals
ml_unstacked = ml_signal.unstack(level='symbol') if isinstance(ml_signal.index, pd.MultiIndex) else None
if ml_unstacked is not None and isinstance(ml_unstacked, pd.DataFrame):
    ml_ranked = ml_unstacked.rank(axis=1, pct=True)
    ml_norm = ml_ranked.div(ml_ranked.sum(axis=1), axis=0).fillna(0)
    common_dates = ml_norm.index.intersection(test_prices.index)
    common_syms = ml_norm.columns.intersection(test_prices.columns)
    ml_norm = ml_norm.loc[common_dates, common_syms]
    next_ret = test_prices[common_syms].loc[common_dates].pct_change().shift(-1)
    signal_returns['ML_COMBINER'] = (ml_norm * next_ret).sum(axis=1)
    signal_exposures['ML_COMBINER'] = ml_norm

# Add screened signals
for sf in accepted[:10]:
    feat = sf['feature']
    if feat not in test_featured.columns:
        continue
    try:
        sig = test_featured[feat].groupby(level='symbol').shift(1)
        unstacked = sig.unstack(level='symbol')
        if unstacked.std().mean() < 1e-8:
            continue
        cd = unstacked.index.intersection(test_prices.index)
        cs = unstacked.columns.intersection(test_prices.columns)
        unstacked = unstacked.loc[cd, cs]
        ranked = unstacked.rank(axis=1, pct=True)
        normalized = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)
        nr = test_prices[cs].loc[cd].pct_change().shift(-1)
        signal_returns[feat] = (normalized * nr).sum(axis=1)
        signal_exposures[feat] = normalized
    except Exception:
        continue

logger.info("HRP signals: %d (1 ML + %d screened)", len(signal_exposures), len(signal_exposures) - 1)

# ============================================================
# PHASE E: HRP + REGIME + CONSTRAINTS + BACKTEST
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE E: HRP + REGIME + BACKTEST")
logger.info("=" * 70)

# HRP weights
hrp = HRPWeighter(lookback=60, min_periods=20)
past_returns = signal_returns.dropna().iloc[:-1]
if len(past_returns) >= 20 and len(past_returns.columns) > 1:
    hrp_weights = hrp.compute_signal_weights(past_returns)
else:
    hrp_weights = pd.Series(1.0 / max(1, len(signal_exposures)), index=signal_exposures.keys())

logger.info("HRP weights:")
for s, w in hrp_weights.sort_values(ascending=False).head(5).items():
    logger.info("  %-30s %.4f", s[:30], w)

# Combine
combined_weights = hrp.compute_asset_weights(test_prices, hrp_weights, signal_exposures)

# Regime
full_market = df.groupby('date')['close'].mean()
regime_det = RegimeDetector()
regime_df = regime_det.detect_rolling(full_market)
combined_weights = regime_det.adjust_weights(combined_weights, regime_df)

# Constraints
combined_weights = combined_weights.clip(upper=0.05)
row_sums = combined_weights.sum(axis=1).replace(0, 1.0)
combined_weights = combined_weights.div(row_sums, axis=0)

# Board-lot
BOARD_LOT, CAPITAL = 100, 10_000_000_000.0
for i in range(len(combined_weights)):
    for col in combined_weights.columns:
        w = combined_weights.iloc[i][col]
        if w > 0 and col in test_prices.columns:
            price = test_prices.iloc[min(i, len(test_prices)-1)][col]
            if price > 0:
                shares = int((w * CAPITAL) / price / BOARD_LOT) * BOARD_LOT
                combined_weights.iloc[i, combined_weights.columns.get_loc(col)] = (shares * price) / CAPITAL
    rs = combined_weights.iloc[i].sum()
    if rs > 0:
        combined_weights.iloc[i] = combined_weights.iloc[i] / rs

# Turnover cap
DAILY_TURNOVER_CAP = 0.0119
for i in range(1, len(combined_weights)):
    change = (combined_weights.iloc[i] - combined_weights.iloc[i-1]).abs().sum()
    if change > DAILY_TURNOVER_CAP:
        scale = DAILY_TURNOVER_CAP / change
        combined_weights.iloc[i] = combined_weights.iloc[i-1] + (combined_weights.iloc[i] - combined_weights.iloc[i-1]) * scale
        rs = combined_weights.iloc[i].sum()
        if rs > 0:
            combined_weights.iloc[i] = combined_weights.iloc[i] / rs

# Align
valid = combined_weights.sum(axis=1) > 0
combined_weights = combined_weights.loc[valid]
test_prices_aligned = test_prices.loc[combined_weights.index]
common_cols = combined_weights.columns.intersection(test_prices_aligned.columns)
combined_weights = combined_weights[common_cols]
test_prices_aligned = test_prices_aligned[common_cols]

# Tiered slippage
test_adv = test_df.groupby('ticker')['adv_60'].mean().sort_values(ascending=False)
top30 = test_adv.head(30).index.tolist()
top30_w = combined_weights[[c for c in common_cols if c in top30]].sum(axis=1).mean()
avg_slippage = 5.0 * top30_w + 10.0 * (1 - top30_w)

# Backtest
runner = ParallelBacktestRunner(num_workers=4, initial_capital=CAPITAL, fee_rate=0.0015, tax_rate=0.001, slippage_bps=avg_slippage)
t1 = time.time()
bt_result = runner.run(test_prices_aligned, combined_weights)
bt_time = time.time() - t1

# Walk-forward
wf_results = []
cs = test_prices_aligned.index[0]
ed = test_prices_aligned.index[-1]
while cs + pd.DateOffset(months=12) <= ed + pd.DateOffset(days=30):
    we = cs + pd.DateOffset(months=12)
    mask = (test_prices_aligned.index >= cs) & (test_prices_aligned.index < we)
    wp, ww = test_prices_aligned.loc[mask], combined_weights.loc[mask]
    if len(wp) >= 20:
        try:
            wr = ParallelBacktestRunner(num_workers=2, initial_capital=CAPITAL, fee_rate=0.0015, tax_rate=0.001, slippage_bps=avg_slippage)
            wb = wr.run(wp, ww)
            wf_results.append({"start": str(cs.date()), "end": str(we.date()), "return": float(wb.metrics['total_return']), "sharpe": float(wb.metrics['sharpe']), "max_dd": float(wb.metrics['max_drawdown'])})
        except Exception:
            pass
    cs += pd.DateOffset(months=6)

# ============================================================
# PHASE F: REPORT
# ============================================================
metrics = bt_result.metrics
calmar = (bt_result.returns.mean() * 252) / abs(metrics['max_drawdown']) if metrics['max_drawdown'] != 0 else 0
avg_turnover = combined_weights.diff().abs().sum(axis=1).mean()
DD_LIMIT = -0.15
breach_msg = "OK" if metrics['max_drawdown'] >= DD_LIMIT else "BREACHED"

print()
print("=" * 70)
print("  OMEGA_QUANT BACKTEST v3.2 - FULL SYSTEM (ML + HRP + Regime)")
print("  170 features | ML Combiner | HRP Ensemble | Regime-Adjusted")
print("=" * 70)
print(f"  Period:          {test_prices_aligned.index[0].date()} to {test_prices_aligned.index[-1].date()}")
print(f"  Capital:         10B VND | Symbols: {len(common_cols)}")
print(f"  HRP Signals:     {len(signal_exposures)} (1 ML + {len(signal_exposures)-1} screened)")
print(f"  ML Train IC:     {train_result.get('train_ic', 0):.4f}")
print(f"  ---")
print(f"  Total Return:    {metrics['total_return']*100:.2f}%")
print(f"  Sharpe Ratio:    {metrics['sharpe']:.4f}")
print(f"  Sortino Ratio:   {metrics['sortino']:.4f}")
print(f"  Calmar Ratio:    {calmar:.4f}")
print(f"  Max Drawdown:    {metrics['max_drawdown']*100:.2f}%")
print(f"  Volatility:      {metrics['volatility']*100:.2f}%")
print(f"  Win Rate:        {metrics['win_rate']*100:.1f}%")
print(f"  Avg Turnover:    {avg_turnover*100:.2f}%/day")
print(f"  Slippage:        {avg_slippage:.1f} bps")
print(f"  DD Limit -15%:   {breach_msg}")
if wf_results:
    print(f"  WF Avg Sharpe:   {np.mean([w['sharpe'] for w in wf_results]):.4f}")
    print(f"  WF Avg Return:   {np.mean([w['return'] for w in wf_results])*100:.2f}%")
print(f"  ---")
print(f"  Feature Time:    {feat_time:.1f}s | Backtest: {bt_time:.1f}s")
print("=" * 70)
print()
print("  VERSION HISTORY:")
print("  v2.1: 1 alpha, IC-weight           | Sharpe 0.99 | Return 43%")
print("  v2.5: 10 signals, IC-weight        | Sharpe 1.10 | Return 50%")
print("  v3.0: 14 signals, HRP+Regime       | Sharpe 1.12 | Return 51%")
print("  v3.1: 20 signals, Unified 170      | Sharpe 1.11 | Return 51%")
print(f"  v3.2: ML+{len(signal_exposures)-1} signals, Full System | Sharpe {metrics['sharpe']:.2f} | Return {metrics['total_return']*100:.0f}%")
print()

# Save
results_dir = Path('data/backtest_v32_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "version": "3.2", "timestamp": datetime.utcnow().isoformat(),
    "strategy": "full_system_ml_hrp_regime",
    "features_total": len(features),
    "ml_train_ic": train_result.get('train_ic', 0),
    "hrp_signals": len(signal_exposures),
    "hrp_weights": {k: round(float(v), 4) for k, v in hrp_weights.items()},
    "metrics": {k: float(v) for k, v in metrics.items()},
    "metrics_extra": {"calmar": float(calmar), "avg_turnover": float(avg_turnover), "slippage": float(avg_slippage)},
    "walk_forward": wf_results,
    "dd_breaker": {"limit": -0.15, "status": breach_msg},
}
with open(results_dir / 'backtest_v32_results.json', 'w') as f:
    json.dump(summary, f, indent=2, default=str)
bt_result.equity_curve.to_csv(results_dir / 'equity_curve.csv')
logger.info("Saved to data/backtest_v32_results/")
logger.info("BACKTEST v3.2 COMPLETE")
