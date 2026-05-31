"""
OMEGA_QUANT Backtest v3.1 - Unified Feature System (165 features)
All 3 feature systems merged: Alt(25) + AltData(8) + Arsenal(132)
Screening across 165 features x 5 horizons = 825 candidates

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 3.1
"""
import sys
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\quant\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\core\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\infra\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\data\src')

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
from omega.quant.evolution.regime_detector import RegimeDetector
from omega.quant.evolution.hrp_weighter import HRPWeighter
from omega.quant.evolution.genetic_alpha import enforce_t_minus_1_lag
from omega.quant.parallel_backtest import ParallelBacktestRunner

# ============================================================
# PHASE A: DATA + UNIFIED FEATURES
# ============================================================
logger.info("=" * 70)
logger.info("BACKTEST v3.1 - UNIFIED FEATURE SYSTEM (165 features)")
logger.info("=" * 70)

df = pd.read_parquet(r'C:\Users\GHC\.openclaw\workspace\data\market_2015_now.parquet')
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

# Generate ALL features via unified adapter
logger.info("Generating unified features (arsenal + alt + data)...")
adapter = UnifiedFeatureAdapter(use_arsenal=True, use_alt_features=True, use_alt_data=True)
t0 = time.time()
val_panel = adapter.generate_all(val_panel)
all_features = adapter.get_all_feature_names()
test_panel = adapter.generate_all(test_panel)
feat_time = time.time() - t0
logger.info("Features: %d total in %.1fs", len(all_features), feat_time)

# ============================================================
# PHASE B: SCREENING 165 features x 5 horizons
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE B: SCREENING %d features x 5 horizons" % len(all_features))
logger.info("=" * 70)

horizons = [1, 3, 5, 10, 20]
screened = []

for horizon in horizons:
    target_col = f'fwd_ret_{horizon}'
    val_h = val_panel.copy()
    val_h[target_col] = val_h.groupby(level='symbol')['close'].pct_change(horizon).shift(-horizon)
    val_h = val_h.dropna(subset=[target_col])

    for feat in all_features:
        if feat not in val_h.columns:
            continue
        try:
            sig = val_h[feat].groupby(level='symbol').shift(1)
            if sig.std() < 1e-8:
                continue
            val_ic = sig.corr(val_h[target_col], method='spearman')
            if np.isnan(val_ic) or abs(val_ic) < 0.03:
                continue
            hit = (np.sign(sig) == np.sign(val_h[target_col])).mean()
            screened.append({'feature': feat, 'horizon': horizon, 'val_ic': float(val_ic), 'hit': float(hit), 'abs_ic': abs(float(val_ic))})
        except Exception:
            continue

screened.sort(key=lambda x: x['abs_ic'], reverse=True)
logger.info("Screened: %d feature-horizon pairs (|IC|>=0.03)", len(screened))

# Orthogonality filter (corr < 0.5)
accepted = []
accepted_sigs = {}
for sa in screened:
    feat = sa['feature']
    try:
        sig = val_panel[feat].groupby(level='symbol').shift(1)
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

logger.info("After orthogonality (corr<0.5): %d diverse signals", len(accepted))
for a in accepted[:10]:
    logger.info("  H%2dd %-30s IC=%.4f hit=%.4f", a['horizon'], a['feature'][:30], a['val_ic'], a['hit'])

# FDR
if len(accepted) > 1:
    p_values = []
    for af in accepted:
        feat, horizon = af['feature'], af['horizon']
        target_col = f'fwd_ret_{horizon}'
        val_h = val_panel.copy()
        val_h[target_col] = val_h.groupby(level='symbol')['close'].pct_change(horizon).shift(-horizon)
        val_h = val_h.dropna(subset=[target_col])
        sig = val_h[feat].groupby(level='symbol').shift(1)
        tgt = val_h[target_col]
        ci = sig.index.intersection(tgt.index)
        try:
            _, pval = stats.spearmanr(sig.loc[ci].values, tgt.loc[ci].values, nan_policy='omit')
            p_values.append(pval if not np.isnan(pval) else 1.0)
        except Exception:
            p_values.append(1.0)
    from statsmodels.stats.multitest import multipletests
    rejected, _, _, _ = multipletests(p_values, alpha=0.10, method='fdr_bh')
    accepted = [a for a, r in zip(accepted, rejected) if r]
    logger.info("FDR (q=0.10): %d survive", len(accepted))

if not accepted:
    logger.error("No features survived. Exiting.")
    sys.exit(1)

# ============================================================
# PHASE C: HRP + REGIME + BACKTEST
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE C: HRP + REGIME + BACKTEST (%d signals)" % len(accepted))
logger.info("=" * 70)

test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()
signal_returns = pd.DataFrame(index=test_prices.index)
signal_exposures = {}

for sf in accepted:
    feat = sf['feature']
    if feat not in test_panel.columns:
        continue
    try:
        sig = test_panel[feat].groupby(level='symbol').shift(1)
        unstacked = sig.unstack(level='symbol')
        if unstacked.std().mean() < 1e-8:
            continue
        common_dates = unstacked.index.intersection(test_prices.index)
        common_syms = unstacked.columns.intersection(test_prices.columns)
        unstacked = unstacked.loc[common_dates, common_syms]
        ranked = unstacked.rank(axis=1, pct=True)
        normalized = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)
        next_ret = test_prices[common_syms].loc[common_dates].pct_change().shift(-1)
        sig_ret = (normalized * next_ret).sum(axis=1)
        signal_returns[feat] = sig_ret
        signal_exposures[feat] = normalized
    except Exception:
        continue

logger.info("Signal exposures: %d", len(signal_exposures))

# HRP
hrp = HRPWeighter(lookback=60, min_periods=20)
past_returns = signal_returns.dropna().iloc[:-1]
if len(past_returns) >= 20 and len(past_returns.columns) > 1:
    hrp_weights = hrp.compute_signal_weights(past_returns)
else:
    hrp_weights = pd.Series(1.0 / max(1, len(signal_exposures)), index=signal_exposures.keys())

logger.info("HRP top 5:")
for s, w in hrp_weights.sort_values(ascending=False).head(5).items():
    logger.info("  %-30s %.4f", s[:30], w)

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

DAILY_TURNOVER_CAP = 0.0119
for i in range(1, len(combined_weights)):
    change = (combined_weights.iloc[i] - combined_weights.iloc[i-1]).abs().sum()
    if change > DAILY_TURNOVER_CAP:
        scale = DAILY_TURNOVER_CAP / change
        combined_weights.iloc[i] = combined_weights.iloc[i-1] + (combined_weights.iloc[i] - combined_weights.iloc[i-1]) * scale
        rs = combined_weights.iloc[i].sum()
        if rs > 0:
            combined_weights.iloc[i] = combined_weights.iloc[i] / rs

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
            wf_results.append({"start": str(cs.date()), "end": str(we.date()), "return": float(wb.metrics['total_return']), "sharpe": float(wb.metrics['sharpe'])})
        except Exception:
            pass
    cs += pd.DateOffset(months=6)

# ============================================================
# REPORT
# ============================================================
metrics = bt_result.metrics
calmar = (bt_result.returns.mean() * 252) / abs(metrics['max_drawdown']) if metrics['max_drawdown'] != 0 else 0
avg_turnover = combined_weights.diff().abs().sum(axis=1).mean()
DD_LIMIT = -0.15
breach_msg = "OK" if metrics['max_drawdown'] >= DD_LIMIT else "BREACHED"

print()
print("=" * 70)
print("  OMEGA_QUANT BACKTEST v3.1 - UNIFIED FEATURE SYSTEM")
print("  165 features (Arsenal 132 + Alt 25 + Data 8) | HRP + Regime")
print("=" * 70)
print(f"  Period:          {test_prices_aligned.index[0].date()} to {test_prices_aligned.index[-1].date()}")
print(f"  Capital:         10B VND | Symbols: {len(common_cols)}")
print(f"  Signals:         {len(accepted)} (from 165 screened)")
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
print("  v2.5: 10 signals (alt only)        | Sharpe 1.10 | Return 50%")
print("  v3.0: 14 signals (alt+data+regime) | Sharpe 1.12 | Return 51%")
print(f"  v3.1: {len(accepted)} signals (UNIFIED 165)    | Sharpe {metrics['sharpe']:.2f} | Return {metrics['total_return']*100:.0f}%")
print()

# Save
results_dir = Path('data/backtest_v31_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "version": "3.1", "timestamp": datetime.utcnow().isoformat(),
    "strategy": "unified_feature_system_165",
    "feature_sources": adapter.get_feature_groups(),
    "total_features_screened": len(all_features),
    "signals_accepted": len(accepted),
    "ensemble": [{"feature": a['feature'][:50], "horizon": a['horizon'], "ic": round(a['val_ic'],4)} for a in accepted],
    "metrics": {k: float(v) for k, v in metrics.items()},
    "metrics_extra": {"calmar": float(calmar), "avg_turnover": float(avg_turnover)},
    "walk_forward": wf_results,
}
with open(results_dir / 'backtest_v31_results.json', 'w') as f:
    json.dump(summary, f, indent=2, default=str)
bt_result.equity_curve.to_csv(results_dir / 'equity_curve.csv')
logger.info("Saved to data/backtest_v31_results/")
logger.info("BACKTEST v3.1 COMPLETE")
