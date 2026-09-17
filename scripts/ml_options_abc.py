"""
OMEGA_QUANT ML Options Comparison (A/B/C)
A: ML alone (no HRP mix)
B: ML + non-overlapping signals only
C: ML forced 60% weight in HRP

Author: Backend Engineer (Role 09)
Date: 2026-05-31
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
from sklearn.linear_model import Ridge

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from omega.quant.evolution.regime_detector import RegimeDetector
from omega.quant.evolution.hrp_weighter import HRPWeighter
from omega.quant.backtest.parallel import ParallelBacktestRunner

# ============================================================
# DATA (same as all versions)
# ============================================================
df = pd.read_parquet(str(Path(__file__).resolve().parents[1] / 'data' / 'market_2015_now.parquet'))
df['date'] = pd.to_datetime(df['date'])
ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
df[ohlcv_cols] = df.groupby('ticker')[ohlcv_cols].ffill(limit=3)
df = df.dropna(subset=['close', 'volume'])
df = df[(df['close'] > 0) & (df['volume'] > 0)]
df['adv_60'] = df.groupby('ticker')['volume'].transform(lambda x: x.rolling(60, min_periods=20).mean())
df = df.dropna(subset=['adv_60'])

VAL_START = pd.Timestamp('2022-08-01')
VAL_END = pd.Timestamp('2024-06-30')
TEST_START = pd.Timestamp('2024-08-01')

val_df = df[(df['date'] >= VAL_START) & (df['date'] <= VAL_END)].copy()
test_df = df[df['date'] >= TEST_START].copy()

def get_pit_universe(period_df, top_n=50):
    last_date = period_df['date'].max()
    recent = period_df[period_df['date'] >= last_date - pd.Timedelta(days=90)]
    return recent.groupby('ticker')['adv_60'].mean().sort_values(ascending=False).head(top_n).index.tolist()

val_df = val_df[val_df['ticker'].isin(get_pit_universe(val_df))]
test_df = test_df[test_df['ticker'].isin(get_pit_universe(test_df))]

def build_panel(period_df):
    panel = period_df.set_index(['date', 'ticker'])[ohlcv_cols].sort_index()
    panel.index.names = ['date', 'symbol']
    panel['returns'] = panel.groupby(level='symbol')['close'].pct_change()
    return panel.dropna(subset=['returns'])

val_panel = build_panel(val_df)
test_panel = build_panel(test_df)

# Features
adapter = UnifiedFeatureAdapter(use_arsenal=True, use_alt_features=True, use_alt_data=True)
val_featured = adapter.generate_all(val_panel)
test_featured = adapter.generate_all(test_panel)
features = adapter.get_all_feature_names()
logger.info("Features: %d", len(features))

# Train ML on VAL
val_h = val_featured.copy()
val_h['fwd_ret_5'] = val_h.groupby(level='symbol')['close'].pct_change(5).shift(-5)
val_h = val_h.dropna(subset=['fwd_ret_5'])
avail_feats = [f for f in features if f in val_h.columns]
X_train = val_h[avail_feats].replace([np.inf, -np.inf], np.nan).fillna(0)
y_train = val_h['fwd_ret_5'].replace([np.inf, -np.inf], np.nan).fillna(0)
model = Ridge(alpha=1.0)
model.fit(X_train.values, y_train.values)
train_ic = pd.Series(model.predict(X_train.values)).corr(y_train.reset_index(drop=True), method='spearman')
logger.info("ML trained: IC=%.4f on %d features", train_ic, len(avail_feats))

# ML signal on TEST
X_test = test_featured[avail_feats].replace([np.inf, -np.inf], np.nan).fillna(0)
ml_preds = model.predict(X_test.values)
ml_signal = pd.Series(ml_preds, index=test_featured.index).groupby(level='symbol').shift(1).fillna(0)

# Test prices
test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()

# Regime
full_market = df.groupby('date')['close'].mean()
regime_det = RegimeDetector()
regime_df = regime_det.detect_rolling(full_market)

# Helper: backtest from weights
CAPITAL = 10_000_000_000.0
def run_backtest(weights_raw, label):
    weights = weights_raw.copy()
    # Regime
    weights = regime_det.adjust_weights(weights, regime_df)
    # Cap 5%
    weights = weights.clip(upper=0.05)
    rs = weights.sum(axis=1).replace(0, 1.0)
    weights = weights.div(rs, axis=0)
    # Turnover
    for i in range(1, len(weights)):
        change = (weights.iloc[i] - weights.iloc[i-1]).abs().sum()
        if change > 0.0119:
            scale = 0.0119 / change
            weights.iloc[i] = weights.iloc[i-1] + (weights.iloc[i] - weights.iloc[i-1]) * scale
            rs2 = weights.iloc[i].sum()
            if rs2 > 0:
                weights.iloc[i] = weights.iloc[i] / rs2
    # Align
    valid = weights.sum(axis=1) > 0
    weights = weights.loc[valid]
    pa = test_prices.loc[weights.index]
    cc = weights.columns.intersection(pa.columns)
    weights = weights[cc]
    pa = pa[cc]
    # Slippage
    test_adv = test_df.groupby('ticker')['adv_60'].mean().sort_values(ascending=False)
    top30 = test_adv.head(30).index.tolist()
    t30w = weights[[c for c in cc if c in top30]].sum(axis=1).mean()
    slip = 5.0 * t30w + 10.0 * (1 - t30w)
    # Run
    runner = ParallelBacktestRunner(num_workers=4, initial_capital=CAPITAL, fee_rate=0.0015, tax_rate=0.001, slippage_bps=slip)
    result = runner.run(pa, weights)
    m = result.metrics
    logger.info("  %s: Sharpe=%.4f, Return=%.2f%%, DD=%.2f%%", label, m['sharpe'], m['total_return']*100, m['max_drawdown']*100)
    return m

# ============================================================
# OPTION A: ML ALONE (no HRP mix)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("OPTION A: ML ALONE (Ridge signal -> weights directly)")
logger.info("=" * 70)

ml_unstacked = ml_signal.unstack(level='symbol')
common_dates = ml_unstacked.index.intersection(test_prices.index)
common_syms = ml_unstacked.columns.intersection(test_prices.columns)
ml_unstacked = ml_unstacked.loc[common_dates, common_syms]
ranked_a = ml_unstacked.rank(axis=1, pct=True)
weights_a = ranked_a.div(ranked_a.sum(axis=1), axis=0).fillna(0)
metrics_a = run_backtest(weights_a, "Option A (ML alone)")

# ============================================================
# OPTION B: ML + NON-OVERLAPPING SIGNALS
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("OPTION B: ML + NON-OVERLAPPING SIGNALS")
logger.info("=" * 70)

# Find signals NOT correlated with ML signal (corr < 0.3)
ml_flat = ml_signal.copy()
non_overlapping = []
for feat in features[:50]:  # Check top 50
    if feat not in test_featured.columns:
        continue
    try:
        sig = test_featured[feat].groupby(level='symbol').shift(1)
        common_idx = ml_flat.index.intersection(sig.index)
        if len(common_idx) > 100:
            corr = ml_flat.loc[common_idx].corr(sig.loc[common_idx])
            if abs(corr) < 0.3:
                non_overlapping.append(feat)
                if len(non_overlapping) >= 5:
                    break
    except Exception:
        continue

logger.info("Non-overlapping signals (corr<0.3 with ML): %d", len(non_overlapping))

# Build HRP with ML (70%) + non-overlapping (30%)
signal_exposures_b = {}
signal_returns_b = pd.DataFrame(index=test_prices.index)

# ML signal
ml_norm_b = weights_a.loc[common_dates, common_syms]
nr = test_prices[common_syms].loc[common_dates].pct_change().shift(-1)
signal_returns_b['ML'] = (ml_norm_b * nr).sum(axis=1)
signal_exposures_b['ML'] = ml_norm_b

# Non-overlapping
for feat in non_overlapping:
    try:
        sig = test_featured[feat].groupby(level='symbol').shift(1)
        unstacked = sig.unstack(level='symbol')
        cd = unstacked.index.intersection(test_prices.index)
        cs = unstacked.columns.intersection(test_prices.columns)
        unstacked = unstacked.loc[cd, cs]
        ranked = unstacked.rank(axis=1, pct=True)
        normalized = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)
        nret = test_prices[cs].loc[cd].pct_change().shift(-1)
        signal_returns_b[feat] = (normalized * nret).sum(axis=1)
        signal_exposures_b[feat] = normalized
    except Exception:
        continue

hrp_b = HRPWeighter(lookback=60, min_periods=20)
past_b = signal_returns_b.dropna().iloc[:-1]
if len(past_b) >= 20 and len(past_b.columns) > 1:
    hrp_w_b = hrp_b.compute_signal_weights(past_b)
else:
    hrp_w_b = pd.Series(1.0/len(signal_exposures_b), index=signal_exposures_b.keys())

weights_b = hrp_b.compute_asset_weights(test_prices, hrp_w_b, signal_exposures_b)
metrics_b = run_backtest(weights_b, "Option B (ML + non-overlap)")
logger.info("  HRP weights B: ML=%.2f, others=%s", hrp_w_b.get('ML', 0), [f"{k}:{v:.2f}" for k,v in hrp_w_b.items() if k != 'ML'])

# ============================================================
# OPTION C: ML FORCED 60% + SCREENED 40%
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("OPTION C: ML FORCED 60% + SCREENED 40%")
logger.info("=" * 70)

# Screen top 10 signals on VAL (same as v3.1)
screened = []
for feat in features:
    if feat not in val_h.columns:
        continue
    try:
        sig = val_h[feat].groupby(level='symbol').shift(1)
        if sig.std() < 1e-8:
            continue
        ic = sig.corr(val_h['fwd_ret_5'], method='spearman')
        if not np.isnan(ic) and abs(ic) >= 0.03:
            screened.append({'feature': feat, 'abs_ic': abs(float(ic))})
    except Exception:
        continue
screened.sort(key=lambda x: x['abs_ic'], reverse=True)

# Orthogonality
accepted_c = []
accepted_sigs_c = {}
for sa in screened:
    feat = sa['feature']
    try:
        sig = val_h[feat].groupby(level='symbol').shift(1)
        if sig.std() < 1e-8:
            continue
        is_diverse = True
        for _, esig in accepted_sigs_c.items():
            common = sig.index.intersection(esig.index)
            if len(common) > 100 and abs(sig.loc[common].corr(esig.loc[common])) > 0.5:
                is_diverse = False
                break
        if is_diverse:
            accepted_c.append(sa)
            accepted_sigs_c[feat] = sig
            if len(accepted_c) >= 10:
                break
    except Exception:
        continue

# Build screened exposures
screened_norm = pd.DataFrame(0.0, index=common_dates, columns=common_syms)
for sa in accepted_c:
    feat = sa['feature']
    if feat not in test_featured.columns:
        continue
    try:
        sig = test_featured[feat].groupby(level='symbol').shift(1)
        unstacked = sig.unstack(level='symbol')
        cd = unstacked.index.intersection(common_dates)
        cs = unstacked.columns.intersection(common_syms)
        ranked = unstacked.loc[cd, cs].rank(axis=1, pct=True)
        normalized = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)
        screened_norm.loc[cd, cs] = screened_norm.loc[cd, cs].values + normalized.values
    except Exception:
        continue
# Normalize screened
rs_scr = screened_norm.sum(axis=1).replace(0, 1.0)
screened_norm = screened_norm.div(rs_scr, axis=0)

# Force 60% ML + 40% screened
weights_c = ml_norm_b * 0.6 + screened_norm.loc[common_dates, common_syms] * 0.4
rs_c = weights_c.sum(axis=1).replace(0, 1.0)
weights_c = weights_c.div(rs_c, axis=0)
metrics_c = run_backtest(weights_c, "Option C (ML 60% + Screened 40%)")

# ============================================================
# FINAL COMPARISON
# ============================================================
print()
print("=" * 70)
print("  ML OPTIONS COMPARISON (A/B/C vs v3.1 Baseline)")
print("=" * 70)
print(f"  {'Option':<35} {'Sharpe':>8} {'Return':>10} {'MaxDD':>10}")
print(f"  {'-'*35} {'-'*8} {'-'*10} {'-'*10}")
print(f"  {'v3.1 Baseline (20 screened, HRP)':<35} {'1.11':>8} {'+51%':>10} {'-21%':>10}")
print(f"  {'A: ML alone':<35} {metrics_a['sharpe']:>8.4f} {metrics_a['total_return']*100:>9.2f}% {metrics_a['max_drawdown']*100:>9.2f}%")
print(f"  {'B: ML + non-overlapping (HRP)':<35} {metrics_b['sharpe']:>8.4f} {metrics_b['total_return']*100:>9.2f}% {metrics_b['max_drawdown']*100:>9.2f}%")
print(f"  {'C: ML 60% + Screened 40%':<35} {metrics_c['sharpe']:>8.4f} {metrics_c['total_return']*100:>9.2f}% {metrics_c['max_drawdown']*100:>9.2f}%")
print("=" * 70)

# Determine winner
all_results = {'A': metrics_a, 'B': metrics_b, 'C': metrics_c}
best_option = max(all_results.items(), key=lambda x: x[1]['sharpe'])
print(f"\n  WINNER: Option {best_option[0]} (Sharpe {best_option[1]['sharpe']:.4f})")
if best_option[1]['sharpe'] > 1.11:
    print("  BEATS v3.1 baseline!")
else:
    print("  Does NOT beat v3.1 baseline (Sharpe 1.11)")
print()

# Save
results_dir = Path('data/ml_options_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "timestamp": datetime.utcnow().isoformat(),
    "baseline_v31": {"sharpe": 1.11, "return": 0.51},
    "option_a_ml_alone": {k: float(v) for k, v in metrics_a.items()},
    "option_b_non_overlap": {k: float(v) for k, v in metrics_b.items()},
    "option_c_forced_60": {k: float(v) for k, v in metrics_c.items()},
    "winner": best_option[0],
}
with open(results_dir / 'ml_options_comparison.json', 'w') as f:
    json.dump(summary, f, indent=2, default=str)
logger.info("Saved to data/ml_options_results/")
