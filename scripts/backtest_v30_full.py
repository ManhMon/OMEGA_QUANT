"""
OMEGA_QUANT Backtest v3.0 - Full Integration
Regime Detector + Alt Features + Alt Data + HRP Weighting + Parallel Backtest

Target: Sharpe > 1.5 via regime-adjusted exposure + HRP diversification

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 3.0
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

from omega.quant.evolution.alternative_features import AlternativeFeatureGenerator
from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher
from omega.quant.evolution.regime_detector import RegimeDetector
from omega.quant.evolution.hrp_weighter import HRPWeighter
from omega.quant.evolution.genetic_alpha import enforce_t_minus_1_lag
from omega.quant.backtest.parallel import ParallelBacktestRunner

# ============================================================
# PHASE A: DATA
# ============================================================
logger.info("=" * 70)
logger.info("BACKTEST v3.0 - FULL INTEGRATION (Regime + HRP + Alt)")
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

# 3-way split with purge
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

# Generate all features
feat_gen = AlternativeFeatureGenerator()
alt_fetcher = AlternativeDataFetcher()
train_panel = alt_fetcher.generate_all(feat_gen.generate_all(train_panel))
val_panel = alt_fetcher.generate_all(feat_gen.generate_all(val_panel))
test_panel = alt_fetcher.generate_all(feat_gen.generate_all(test_panel))
logger.info("Panels: train=%d, val=%d, test=%d (%d features)", len(train_panel), len(val_panel), len(test_panel), len(test_panel.columns))

# ============================================================
# PHASE B: FEATURE SCREENING ON VALIDATION (same as v2.5)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE B: FEATURE SCREENING (validation period)")
logger.info("=" * 70)

all_features = feat_gen.get_feature_names() + alt_fetcher.get_feature_names()
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
            if np.isnan(val_ic) or abs(val_ic) < 0.02:
                continue
            hit = (np.sign(sig) == np.sign(val_h[target_col])).mean()
            screened.append({'feature': feat, 'horizon': horizon, 'val_ic': float(val_ic), 'hit': float(hit), 'abs_ic': abs(float(val_ic))})
        except Exception:
            continue

screened.sort(key=lambda x: x['abs_ic'], reverse=True)
logger.info("Screened: %d feature-horizon pairs (|IC|>=0.02)", len(screened))

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
            if len(accepted) >= 14:
                break
    except Exception:
        continue

logger.info("After orthogonality: %d diverse signals", len(accepted))
for a in accepted[:5]:
    logger.info("  H%dd %-22s IC=%.4f", a['horizon'], a['feature'], a['val_ic'])

# ============================================================
# PHASE C: HRP + REGIME ON TEST PERIOD
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE C: HRP WEIGHTING + REGIME ADJUSTMENT (TEST)")
logger.info("=" * 70)

test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()

# Build signal exposures
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
        # Signal return for HRP
        next_ret = test_prices[common_syms].loc[common_dates].pct_change().shift(-1)
        sig_ret = (normalized * next_ret).sum(axis=1)
        signal_returns[feat] = sig_ret
        signal_exposures[feat] = normalized
    except Exception:
        continue

logger.info("Signal exposures built: %d signals", len(signal_exposures))

# HRP weights
hrp = HRPWeighter(lookback=60, min_periods=20)
past_returns = signal_returns.dropna().iloc[:-1]
if len(past_returns) >= 20 and len(past_returns.columns) > 1:
    hrp_weights = hrp.compute_signal_weights(past_returns)
else:
    hrp_weights = pd.Series(1.0 / max(1, len(signal_exposures)), index=signal_exposures.keys())

logger.info("HRP weights (top 5):")
for s, w in hrp_weights.sort_values(ascending=False).head(5).items():
    logger.info("  %-22s %.4f", s, w)

# Combine with HRP
combined_weights = hrp.compute_asset_weights(test_prices, hrp_weights, signal_exposures)

# Regime adjustment (rolling)
market_prices = test_panel['close'].groupby(level='date').mean()
# Need enough history for MA200 - use full data
full_market = df.groupby('date')['close'].mean()
regime_det = RegimeDetector()
regime_df = regime_det.detect_rolling(full_market)
logger.info("Regime rolling: %d dates computed", len(regime_df))

# Apply regime to test weights
combined_weights = regime_det.adjust_weights(combined_weights, regime_df)
logger.info("Regime-adjusted weights applied")

# ============================================================
# PHASE D: CONSTRAINTS + PARALLEL BACKTEST
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE D: CONSTRAINTS + BACKTEST")
logger.info("=" * 70)

# Max 5% single name
combined_weights = combined_weights.clip(upper=0.05)
row_sums = combined_weights.sum(axis=1).replace(0, 1.0)
combined_weights = combined_weights.div(row_sums, axis=0)

# Board-lot rounding
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

# Turnover cap 1.19%/day
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
t0 = time.time()
bt_result = runner.run(test_prices_aligned, combined_weights)
bt_time = time.time() - t0

# DD check
DD_LIMIT = -0.15
breach_msg = "OK"
if bt_result.metrics['max_drawdown'] < DD_LIMIT:
    eq = bt_result.equity_curve
    dd = (eq - eq.expanding().max()) / eq.expanding().max()
    bd = dd[dd < DD_LIMIT].index[0] if (dd < DD_LIMIT).any() else None
    breach_msg = f"BREACHED (halt @ {bd.date()})" if bd else "BREACHED"

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
# PHASE E: REPORT
# ============================================================
metrics = bt_result.metrics
calmar = (bt_result.returns.mean() * 252) / abs(metrics['max_drawdown']) if metrics['max_drawdown'] != 0 else 0
avg_turnover = combined_weights.diff().abs().sum(axis=1).mean()

print()
print("=" * 70)
print("  OMEGA_QUANT BACKTEST v3.0 - FULL INTEGRATION")
print("  Regime + HRP + Alt Features + Alt Data | Production Grade")
print("=" * 70)
print(f"  Period:          {test_prices_aligned.index[0].date()} to {test_prices_aligned.index[-1].date()}")
print(f"  Capital:         10B VND | Symbols: {len(common_cols)}")
print(f"  Signals:         {len(accepted)} (HRP-weighted)")
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
print(f"  Backtest Time:   {bt_time:.1f}s")
print("=" * 70)
print()
print("  VERSION HISTORY:")
print("  v2.1: 1 alpha, IC-weight      | Sharpe 0.99 | Return 43%")
print("  v2.5: 10 signals, IC-weight   | Sharpe 1.10 | Return 50%")
print(f"  v3.0: {len(accepted)} signals, HRP+Regime | Sharpe {metrics['sharpe']:.2f} | Return {metrics['total_return']*100:.0f}%")
print()

# Save
results_dir = Path('data/backtest_v30_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "version": "3.0", "timestamp": datetime.utcnow().isoformat(),
    "strategy": "full_integration_regime_hrp_alt",
    "signals": len(accepted),
    "ensemble": [{"feature": a['feature'], "horizon": a['horizon'], "ic": a['val_ic']} for a in accepted],
    "hrp_weights": {k: round(float(v), 4) for k, v in hrp_weights.items()},
    "metrics": {k: float(v) for k, v in metrics.items()},
    "metrics_extra": {"calmar": float(calmar), "avg_turnover": float(avg_turnover), "slippage_bps": float(avg_slippage)},
    "walk_forward": wf_results,
    "dd_breaker": {"limit": -0.15, "status": breach_msg},
}
with open(results_dir / 'backtest_v30_results.json', 'w') as f:
    json.dump(summary, f, indent=2, default=str)
bt_result.equity_curve.to_csv(results_dir / 'equity_curve.csv')
logger.info("Saved to data/backtest_v30_results/")
logger.info("BACKTEST v3.0 COMPLETE")
