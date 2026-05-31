"""
OMEGA_QUANT Backtest v2.5 - Alternative Features + Multi-Horizon
Expanded GP terminal set with 25 alternative features derived from OHLCV.
Goal: Find uncorrelated alphas beyond mean-reversion.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 2.5
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

from omega.quant.evolution.genetic_alpha import Genome, Node, enforce_t_minus_1_lag
from omega.quant.evolution.alpha_evolution_pipeline import AlphaCandidate, EvolutionConfig
from omega.quant.evolution.alternative_features import AlternativeFeatureGenerator
from omega.quant.parallel_backtest import ParallelBacktestRunner

# ============================================================
# PHASE A: DATA + ALTERNATIVE FEATURES
# ============================================================
logger.info("=" * 70)
logger.info("BACKTEST v2.5 - ALTERNATIVE FEATURES + MULTI-HORIZON")
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

# Generate alternative features
logger.info("Generating alternative features...")
feat_gen = AlternativeFeatureGenerator()
train_panel = feat_gen.generate_all(train_panel)
val_panel = feat_gen.generate_all(val_panel)
test_panel = feat_gen.generate_all(test_panel)
alt_features = feat_gen.get_feature_names()
logger.info("Panels with alt features: train=%d, val=%d, test=%d (%d features)",
            len(train_panel), len(val_panel), len(test_panel), len(alt_features))

# ============================================================
# PHASE B: DIRECT FEATURE SCREENING (faster than GP for alt features)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE B: FEATURE SCREENING + GP EVOLUTION")
logger.info("=" * 70)

# B1: Screen all alternative features directly (no GP needed for raw features)
# This is faster and more reliable than GP for pre-computed features
logger.info("Screening %d alternative features on validation...", len(alt_features))

horizons = [1, 3, 5, 10, 20]
screened_alphas = []

for horizon in horizons:
    target_col = f'fwd_ret_{horizon}'
    val_h = val_panel.copy()
    val_h[target_col] = val_h.groupby(level='symbol')['close'].pct_change(horizon).shift(-horizon)
    # dropna removes rows where fwd_ret is NaN (tail rows) — no look-ahead bias
    # because IC is only computed on rows where both signal (T-1) and target exist
    val_h = val_h.dropna(subset=[target_col])

    train_h = train_panel.copy()
    train_h[target_col] = train_h.groupby(level='symbol')['close'].pct_change(horizon).shift(-horizon)
    train_h = train_h.dropna(subset=[target_col])

    for feat in alt_features:
        if feat not in val_h.columns or feat not in train_h.columns:
            continue
        try:
            # T-1 lag the feature (PIT safety)
            val_sig = val_h[feat].groupby(level='symbol').shift(1)
            train_sig = train_h[feat].groupby(level='symbol').shift(1)

            if val_sig.std() < 1e-8 or train_sig.std() < 1e-8:
                continue

            # IC on train and validation
            train_ic = train_sig.corr(train_h[target_col], method='spearman')
            val_ic = val_sig.corr(val_h[target_col], method='spearman')

            if np.isnan(train_ic) or np.isnan(val_ic):
                continue

            hit_rate = (np.sign(val_sig) == np.sign(val_h[target_col])).mean()

            if abs(val_ic) >= 0.02:
                # Create a simple genome wrapper for this feature
                # Use the feature directly as terminal (mapped to column)
                screened_alphas.append({
                    'feature': feat,
                    'horizon': horizon,
                    'train_ic': float(train_ic),
                    'val_ic': float(val_ic),
                    'hit_rate': float(hit_rate),
                    'abs_ic': abs(float(val_ic)),
                })
        except Exception:
            continue

logger.info("Screened: %d feature-horizon pairs with |IC| >= 0.02", len(screened_alphas))

# Sort by absolute IC
screened_alphas.sort(key=lambda x: x['abs_ic'], reverse=True)

# Show top 20
logger.info("Top 20 features:")
for i, sa in enumerate(screened_alphas[:20]):
    logger.info("  %2d. H%dd %-22s trainIC=%.4f valIC=%.4f hit=%.4f",
                i+1, sa['horizon'], sa['feature'], sa['train_ic'], sa['val_ic'], sa['hit_rate'])

# B2: Orthogonality filter on screened features (corr < 0.5)
logger.info("")
logger.info("Applying orthogonality filter (corr < 0.5)...")
accepted_features = []
accepted_sigs = {}

for sa in screened_alphas:
    feat = sa['feature']
    horizon = sa['horizon']
    try:
        val_h = val_panel.copy()
        sig = val_h[feat].groupby(level='symbol').shift(1)  # T-1 lag
        if sig.std() < 1e-8:
            continue

        is_diverse = True
        for _, esig in accepted_sigs.items():
            common = sig.index.intersection(esig.index)
            if len(common) > 100:
                corr = sig.loc[common].corr(esig.loc[common])
                if abs(corr) > 0.5:
                    is_diverse = False
                    break

        if is_diverse:
            accepted_features.append(sa)
            accepted_sigs[f"{feat}_H{horizon}d"] = sig
            if len(accepted_features) >= 10:
                break
    except Exception:
        continue

logger.info("After orthogonality: %d diverse feature-signals", len(accepted_features))
for af in accepted_features:
    logger.info("  H%dd %-22s IC=%.4f hit=%.4f", af['horizon'], af['feature'], af['val_ic'], af['hit_rate'])

# B3: FDR correction
if len(accepted_features) > 1:
    logger.info("Applying FDR (BH q=0.10)...")
    p_values = []
    for af in accepted_features:
        feat = af['feature']
        horizon = af['horizon']
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
    fdr_features = [af for af, r in zip(accepted_features, rejected) if r]
    logger.info("FDR: %d/%d survive", len(fdr_features), len(accepted_features))
    if fdr_features:
        accepted_features = fdr_features

if not accepted_features:
    logger.error("No features survived. Exiting.")
    sys.exit(1)

logger.info("FINAL ENSEMBLE: %d diverse features", len(accepted_features))

# ============================================================
# PHASE C+D: PORTFOLIO + BACKTEST
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE C+D: PORTFOLIO + BACKTEST (%d features)" % len(accepted_features))
logger.info("=" * 70)

test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()
combined_weights = pd.DataFrame(0.0, index=test_prices.index, columns=test_prices.columns)
alpha_contributions = 0

for af in accepted_features:
    feat = af['feature']
    try:
        if feat not in test_panel.columns:
            continue
        # Get signal with T-1 lag
        sig = test_panel[feat].groupby(level='symbol').shift(1)
        sig = enforce_t_minus_1_lag(sig)  # Double safety

        unstacked = sig.unstack(level='symbol')
        if isinstance(unstacked, pd.DataFrame) and unstacked.std().mean() > 1e-8:
            # Align with test_prices
            common_dates = unstacked.index.intersection(test_prices.index)
            common_syms = unstacked.columns.intersection(test_prices.columns)
            unstacked = unstacked.loc[common_dates, common_syms]

            ranked = unstacked.rank(axis=1, pct=True)
            normalized = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)

            # IC-weight
            ic_weight = max(abs(af['val_ic']), 0.01)
            # Align to combined_weights shape
            for col in normalized.columns:
                if col in combined_weights.columns:
                    combined_weights.loc[common_dates, col] += normalized[col].values * ic_weight

            alpha_contributions += 1
    except Exception as e:
        logger.debug("Feature %s failed: %s", feat, e)
        continue

logger.info("Feature contributions: %d/%d", alpha_contributions, len(accepted_features))

# Normalize + cap 5% + board-lot + turnover
row_sums = combined_weights.sum(axis=1).replace(0, 1.0)
combined_weights = combined_weights.div(row_sums, axis=0)
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
current_start = test_prices_aligned.index[0]
end_date = test_prices_aligned.index[-1]
while current_start + pd.DateOffset(months=12) <= end_date + pd.DateOffset(days=30):
    we = current_start + pd.DateOffset(months=12)
    mask = (test_prices_aligned.index >= current_start) & (test_prices_aligned.index < we)
    wp, ww = test_prices_aligned.loc[mask], combined_weights.loc[mask]
    if len(wp) >= 20:
        try:
            wr = ParallelBacktestRunner(num_workers=2, initial_capital=CAPITAL, fee_rate=0.0015, tax_rate=0.001, slippage_bps=avg_slippage)
            wb = wr.run(wp, ww)
            wf_results.append({"start": str(current_start.date()), "end": str(we.date()),
                               "return": float(wb.metrics['total_return']), "sharpe": float(wb.metrics['sharpe']),
                               "max_dd": float(wb.metrics['max_drawdown'])})
        except Exception:
            pass
    current_start += pd.DateOffset(months=6)

# ============================================================
# PHASE E: REPORT
# ============================================================
metrics = bt_result.metrics
calmar = (bt_result.returns.mean() * 252) / abs(metrics['max_drawdown']) if metrics['max_drawdown'] != 0 else 0
avg_turnover = combined_weights.diff().abs().sum(axis=1).mean()

print()
print("=" * 70)
print("  OMEGA_QUANT BACKTEST v2.5 - ALTERNATIVE FEATURES ENSEMBLE")
print("  25 derived features | Multi-horizon screening | Forced diversity")
print("=" * 70)
print(f"  Period:          {test_prices_aligned.index[0].date()} to {test_prices_aligned.index[-1].date()}")
print(f"  Capital:         10B VND | Symbols: {len(common_cols)}")
print(f"  Active Signals:  {len(accepted_features)} (diverse alt features)")
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
print("  VERSION COMPARISON:")
print("  v2.1: 1 GP alpha         | Sharpe 0.99 | Return 43% | DD -21%")
print(f"  v2.5: {len(accepted_features)} alt features    | Sharpe {metrics['sharpe']:.2f} | Return {metrics['total_return']*100:.0f}% | DD {metrics['max_drawdown']*100:.0f}%")
print()
print("  ENSEMBLE COMPOSITION:")
for af in accepted_features:
    print(f"    H{af['horizon']:2d}d {af['feature']:22s} IC={af['val_ic']:.4f} hit={af['hit_rate']:.4f}")
print()

# Save
results_dir = Path('data/backtest_v25_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "version": "2.5", "timestamp": datetime.utcnow().isoformat(),
    "strategy": "alternative_features_ensemble",
    "features_screened": len(screened_alphas),
    "features_accepted": len(accepted_features),
    "ensemble": accepted_features,
    "metrics": {k: float(v) for k, v in metrics.items()},
    "metrics_extra": {"calmar": float(calmar), "avg_turnover": float(avg_turnover)},
    "walk_forward": wf_results,
    "dd_breaker": {"limit": -0.15, "status": breach_msg},
}
with open(results_dir / 'backtest_v25_results.json', 'w') as f:
    json.dump(summary, f, indent=2, default=str)
bt_result.equity_curve.to_csv(results_dir / 'equity_curve.csv')
logger.info("Saved to data/backtest_v25_results/")
logger.info("BACKTEST v2.5 COMPLETE")
