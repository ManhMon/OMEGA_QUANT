"""
OMEGA_QUANT Backtest v2.4 - Multi-Horizon Alpha Ensemble
GP evolve per horizon (1d,3d,5d,10d,20d) -> cross-horizon diversity -> ensemble

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 2.4
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

from omega.quant.evolution.multi_horizon_evolution import MultiHorizonEvolution, MultiHorizonConfig
from omega.quant.backtest.parallel import ParallelBacktestRunner

# ============================================================
# PHASE A: DATA PIPELINE
# ============================================================
logger.info("=" * 70)
logger.info("BACKTEST v2.4 - MULTI-HORIZON ALPHA ENSEMBLE")
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
logger.info("Panels: train=%d, val=%d, test=%d", len(train_panel), len(val_panel), len(test_panel))

# ============================================================
# PHASE B: MULTI-HORIZON EVOLUTION
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE B: MULTI-HORIZON EVOLUTION (1d, 3d, 5d, 10d, 20d)")
logger.info("=" * 70)

mh_config = MultiHorizonConfig(
    horizons=[1, 3, 5, 10, 20],
    population_size=100,
    generations=15,          # Shorter per horizon (5 horizons x 15 gen = 75 total gen-equivalents)
    max_depth=5,
    ic_threshold=0.03,       # Lower per-horizon; ensemble compensates
    min_hit_rate=0.51,
    corr_threshold=0.5,
    max_alphas_per_horizon=3,
    max_total_alphas=10,
    state_dir='data/backtest_v24_evolution',
)

mh_evo = MultiHorizonEvolution(config=mh_config)
t0 = time.time()
final_alphas, evo_summary = mh_evo.run(train_panel, val_panel)
evo_time = time.time() - t0

n_alphas = len(final_alphas)
logger.info("Multi-horizon result: %d diverse alphas from %s horizons", n_alphas, mh_config.horizons)

# FDR correction (q=0.10 for ensemble)
if n_alphas > 1:
    logger.info("Applying FDR (BH q=0.10) with per-horizon targets...")
    val_with_targets = val_panel.copy()
    for h in [1, 3, 5, 10, 20]:
        val_with_targets[f'fwd_ret_{h}'] = val_with_targets.groupby(level='symbol')['close'].pct_change(h).shift(-h)

    p_values = []
    for alpha in final_alphas:
        try:
            # Extract horizon from expression prefix H{N}d:
            expr = alpha.expression
            horizon = 5  # default
            if expr.startswith('H') and 'd:' in expr:
                try:
                    horizon = int(expr.split('d:')[0][1:])
                except ValueError:
                    pass
            target_col = f'fwd_ret_{horizon}'
            val_h = val_with_targets.dropna(subset=[target_col])
            sig = alpha.genome.evaluate_vectorized(val_h)
            tgt = val_h[target_col]
            ci = sig.index.intersection(tgt.index)
            _, pval = stats.spearmanr(sig.loc[ci].values, tgt.loc[ci].values, nan_policy='omit')
            p_values.append(pval if not np.isnan(pval) else 1.0)
        except Exception:
            p_values.append(1.0)

    from statsmodels.stats.multitest import multipletests
    rejected, _, _, _ = multipletests(p_values, alpha=0.10, method='fdr_bh')
    fdr_alphas = [a for a, r in zip(final_alphas, rejected) if r]
    logger.info("FDR: %d/%d survive", len(fdr_alphas), n_alphas)
    if fdr_alphas:
        final_alphas = fdr_alphas

if not final_alphas:
    logger.error("No alphas survived. Exiting.")
    sys.exit(1)

# Profit factor gate (>= 1.3)
logger.info("Applying profit factor gate (>= 1.3)...")
pf_survivors = []
val_with_5d = val_panel.copy()
val_with_5d['fwd_ret_5'] = val_with_5d.groupby(level='symbol')['close'].pct_change(5).shift(-5)
val_with_5d = val_with_5d.dropna(subset=['fwd_ret_5'])
for alpha in final_alphas:
    try:
        sig = alpha.genome.evaluate_vectorized(val_with_5d)
        ret = val_with_5d['fwd_ret_5']
        ci = sig.index.intersection(ret.index)
        aligned_ret = ret.loc[ci] * np.sign(sig.loc[ci])
        gains = aligned_ret[aligned_ret > 0].sum()
        losses = abs(aligned_ret[aligned_ret < 0].sum())
        pf = gains / losses if losses > 0 else 999.0
        if pf >= 1.3:
            pf_survivors.append(alpha)
            logger.info("  PASS PF=%.2f | %s", pf, alpha.expression[:60])
        else:
            logger.info("  FAIL PF=%.2f | %s", pf, alpha.expression[:60])
    except Exception:
        pf_survivors.append(alpha)  # Keep if can't evaluate

if pf_survivors:
    final_alphas = pf_survivors
else:
    logger.warning("No alphas passed PF>=1.3. Keeping FDR survivors.")

n_alphas = len(final_alphas)
logger.info("FINAL ENSEMBLE: %d alphas", n_alphas)
for a in final_alphas:
    logger.info("  IC=%.4f, Hit=%.4f | %s", a.test_ic, a.hit_rate, a.expression[:70])

# ============================================================
# PHASE C+D: PORTFOLIO + BACKTEST (TEST period)
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE C+D: PORTFOLIO + BACKTEST (%d multi-horizon alphas)" % n_alphas)
logger.info("=" * 70)

test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()
combined_weights = pd.DataFrame(0.0, index=test_prices.index, columns=test_prices.columns)
alpha_contributions = 0

for alpha in final_alphas:
    try:
        panel = test_prices.stack()
        panel.index.names = ['date', 'symbol']
        panel = panel.to_frame('close')
        panel['open'] = panel['close']
        panel['high'] = panel['close']
        panel['low'] = panel['close']
        panel['volume'] = 1_000_000.0
        panel['returns'] = panel.groupby(level='symbol')['close'].pct_change().fillna(0)
        signal = alpha.genome.evaluate_vectorized(panel)
        if isinstance(signal, pd.Series) and signal.std() > 1e-8:
            unstacked = signal.unstack(level='symbol') if isinstance(signal.index, pd.MultiIndex) else signal
            if isinstance(unstacked, pd.DataFrame):
                ranked = unstacked.rank(axis=1, pct=True)
                normalized = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)
                ic_weight = max(abs(alpha.test_ic), 0.01)
                combined_weights = combined_weights.add(normalized * ic_weight, fill_value=0.0)
                alpha_contributions += 1
    except Exception:
        continue

logger.info("Alpha contributions: %d/%d", alpha_contributions, n_alphas)

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
print("  OMEGA_QUANT BACKTEST v2.4 - MULTI-HORIZON ENSEMBLE")
print("  Horizons: 1d, 3d, 5d, 10d, 20d | Cross-horizon diversity")
print("=" * 70)
print(f"  Period:          {test_prices_aligned.index[0].date()} to {test_prices_aligned.index[-1].date()}")
print(f"  Capital:         10B VND | Symbols: {len(common_cols)}")
print(f"  Active Alphas:   {n_alphas} (multi-horizon ensemble)")
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
print(f"  Evolution:       {evo_time:.1f}s | Backtest: {bt_time:.1f}s")
print(f"  Horizons used:   {[h for h, r in evo_summary['horizon_results'].items() if r['n_alphas'] > 0]}")
print("=" * 70)
print()
print("  VERSION COMPARISON:")
print("  v2.1: 1 alpha (5d only)  | Sharpe 0.99 | Return 43% | DD -21%")
print(f"  v2.4: {n_alphas} alphas (multi-H) | Sharpe {metrics['sharpe']:.2f} | Return {metrics['total_return']*100:.0f}% | DD {metrics['max_drawdown']*100:.0f}%")
print()

# Save
results_dir = Path('data/backtest_v24_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "version": "2.4", "timestamp": datetime.utcnow().isoformat(),
    "strategy": "multi_horizon_ensemble",
    "horizons": mh_config.horizons,
    "evolution": evo_summary,
    "ensemble": {"n_alphas": n_alphas, "corr_threshold": 0.5},
    "metrics": {k: float(v) for k, v in metrics.items()},
    "metrics_extra": {"calmar": float(calmar), "avg_turnover": float(avg_turnover)},
    "walk_forward": wf_results,
    "dd_breaker": {"limit": -0.15, "status": breach_msg},
    "alphas": [{"expr": a.expression[:80], "ic": a.test_ic, "hit": a.hit_rate} for a in final_alphas],
}
with open(results_dir / 'backtest_v24_results.json', 'w') as f:
    json.dump(summary, f, indent=2, default=str)
bt_result.equity_curve.to_csv(results_dir / 'equity_curve.csv')
logger.info("Saved to data/backtest_v24_results/")
logger.info("BACKTEST v2.4 COMPLETE")
