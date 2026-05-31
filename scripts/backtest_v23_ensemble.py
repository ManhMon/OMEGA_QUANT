"""
OMEGA_QUANT Backtest v2.3 - Multi-Strategy Ensemble
Strategy: GP best alpha + seeded family alphas (forced uncorrelated)
Key insight: N weak uncorrelated alphas > 1 strong alpha (Sharpe ~ sqrt(N))

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 2.3
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
from omega.quant.evolution.alpha_evolution_pipeline import AlphaEvolutionPipeline, AlphaCandidate, EvolutionConfig
from omega.quant.parallel_backtest import ParallelBacktestRunner

# ============================================================
# PHASE A: DATA (same pipeline)
# ============================================================
logger.info("=" * 70)
logger.info("PHASE A: DATA PIPELINE")
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
    panel['fwd_ret_5'] = panel.groupby(level='symbol')['close'].pct_change(5).shift(-5)
    return panel.dropna(subset=['returns'])

train_panel = build_panel(train_df)
val_panel = build_panel(val_df)
test_panel = build_panel(test_df)
logger.info("Panels: train=%d, val=%d, test=%d", len(train_panel), len(val_panel), len(test_panel))

# ============================================================
# PHASE B: MULTI-STRATEGY ENSEMBLE
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE B: MULTI-STRATEGY ENSEMBLE (GP + Seeded Families)")
logger.info("=" * 70)

# B1: GP Evolution (get best alpha)
evo_config = EvolutionConfig(
    population_size=150, generations=25, max_depth=5,
    mutation_rate=0.35, crossover_rate=0.6, elitism_count=5,
    ic_threshold=0.03, decay_threshold=0.5, corr_threshold=0.7,
    min_hit_rate=0.51, backtest_workers=4,
    state_dir='data/backtest_v23_evolution', max_active_alphas=15,
)
pipeline = AlphaEvolutionPipeline(config=evo_config)
t0 = time.time()
evo_result = pipeline.run(train_panel, val_panel, target_col='fwd_ret_5', prices=None, n_generations=25)
evo_time = time.time() - t0
gp_alphas = list(pipeline.active_alphas)
logger.info("GP: %d alphas evolved in %.1fs", len(gp_alphas), evo_time)

# B2: Seeded Family Alphas (known archetypes, evaluated on validation)
logger.info("Evaluating seeded alpha families on validation...")

FAMILY_TREES = {
    "momentum_5d": Node('rank', [Node('delay', [Node('returns')])]),
    "mean_rev": Node('min', [Node('mean', [Node('returns')])]),
    "vol_rank": Node('rank', [Node('std', [Node('close')])]),
    "volume_surge": Node('rank', [Node('std', [Node('volume')])]),
    "hl_range": Node('div', [Node('sub', [Node('high'), Node('low')]), Node('close')]),
    "price_vol_div": Node('sub', [Node('rank', [Node('close')]), Node('rank', [Node('volume')])]),
}

seeded_alphas = []
for name, tree in FAMILY_TREES.items():
    try:
        genome = Genome(tree=tree)
        train_sig = genome.evaluate_vectorized(train_panel)
        val_sig = genome.evaluate_vectorized(val_panel)
        if train_sig.std() < 1e-8 or val_sig.std() < 1e-8:
            continue
        train_ic = train_sig.corr(train_panel['fwd_ret_5'], method='spearman')
        val_ic = val_sig.corr(val_panel['fwd_ret_5'], method='spearman')
        hit = (np.sign(val_sig) == np.sign(val_panel['fwd_ret_5'])).mean()
        if np.isnan(val_ic):
            continue
        candidate = AlphaCandidate(
            genome=genome, expression=f"SEED:{name}",
            train_ic=float(train_ic), test_ic=float(val_ic), hit_rate=float(hit),
        )
        seeded_alphas.append(candidate)
        logger.info("  %s: trainIC=%.4f, valIC=%.4f, hit=%.4f", name, train_ic, val_ic, hit)
    except Exception as e:
        logger.debug("Seed %s failed: %s", name, e)

# B3: Combine GP + Seeded, filter by relaxed gate (IC>0.02 for ensemble benefit)
all_alphas = gp_alphas + seeded_alphas
logger.info("Total candidates: %d GP + %d seeded = %d", len(gp_alphas), len(seeded_alphas), len(all_alphas))

# Incremental orthogonality filter (corr < 0.5)
accepted = []
accepted_sigs = {}
for alpha in sorted(all_alphas, key=lambda a: a.test_ic, reverse=True):
    try:
        sig = alpha.genome.evaluate_vectorized(val_panel)
        if sig.std() < 1e-8:
            continue
        # Check vs accepted
        is_diverse = True
        for _, esig in accepted_sigs.items():
            if abs(sig.corr(esig)) > 0.5:
                is_diverse = False
                break
        if is_diverse and alpha.test_ic >= 0.02:
            accepted.append(alpha)
            accepted_sigs[alpha.expression[:50]] = sig
            if len(accepted) >= 10:
                break
    except Exception:
        continue

logger.info("Ensemble after orthogonality (corr<0.5, IC>0.02): %d alphas", len(accepted))

# B4: FDR on accepted
if len(accepted) > 1:
    p_values = []
    for alpha in accepted:
        try:
            sig = alpha.genome.evaluate_vectorized(val_panel)
            tgt = val_panel['fwd_ret_5']
            ci = sig.index.intersection(tgt.index)
            _, pval = stats.spearmanr(sig.loc[ci].values, tgt.loc[ci].values, nan_policy='omit')
            p_values.append(pval if not np.isnan(pval) else 1.0)
        except Exception:
            p_values.append(1.0)
    from statsmodels.stats.multitest import multipletests
    rejected, _, _, _ = multipletests(p_values, alpha=0.10, method='fdr_bh')  # q=0.10 for ensemble
    final_alphas = [a for a, r in zip(accepted, rejected) if r]
    logger.info("FDR (q=0.10): %d/%d survive", len(final_alphas), len(accepted))
else:
    final_alphas = accepted

if not final_alphas:
    final_alphas = accepted[:3] if accepted else gp_alphas[:1]
    logger.warning("Fallback: using top %d alphas without FDR", len(final_alphas))

logger.info("FINAL ENSEMBLE: %d alphas", len(final_alphas))
for a in final_alphas:
    logger.info("  IC=%.4f, Hit=%.4f | %s", a.test_ic, a.hit_rate, a.expression[:60])

# ============================================================
# PHASE C+D: PORTFOLIO + BACKTEST
# ============================================================
logger.info("")
logger.info("=" * 70)
logger.info("PHASE C+D: PORTFOLIO + BACKTEST (%d alphas ensemble)" % len(final_alphas))
logger.info("=" * 70)

test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()
n_alphas = len(final_alphas)
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
                               "return": float(wb.metrics['total_return']), "sharpe": float(wb.metrics['sharpe'])})
        except Exception:
            pass
    current_start += pd.DateOffset(months=6)

# Report
metrics = bt_result.metrics
calmar = (bt_result.returns.mean() * 252) / abs(metrics['max_drawdown']) if metrics['max_drawdown'] != 0 else 0
avg_turnover = combined_weights.diff().abs().sum(axis=1).mean()

print()
print("=" * 70)
print("  OMEGA_QUANT BACKTEST v2.3 - MULTI-STRATEGY ENSEMBLE")
print("  GP Best + Seeded Families | Forced Diversity (corr<0.5)")
print("=" * 70)
print(f"  Period:          {test_prices_aligned.index[0].date()} to {test_prices_aligned.index[-1].date()}")
print(f"  Capital:         10B VND | Symbols: {len(common_cols)}")
print(f"  Active Alphas:   {n_alphas} (ensemble)")
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
print("=" * 70)

# Compare versions
print()
print("  VERSION COMPARISON:")
print("  v2.1: 1 alpha  | Sharpe 0.99 | Return 43% | DD -21%")
print(f"  v2.3: {n_alphas} alphas | Sharpe {metrics['sharpe']:.2f} | Return {metrics['total_return']*100:.0f}% | DD {metrics['max_drawdown']*100:.0f}%")
print()

# Save
results_dir = Path('data/backtest_v23_results')
results_dir.mkdir(parents=True, exist_ok=True)
summary = {
    "version": "2.3", "timestamp": datetime.utcnow().isoformat(),
    "strategy": "multi_strategy_ensemble_gp_plus_seeded",
    "evolution": {"duration_s": evo_time, "gp_alphas": len(gp_alphas), "seeded_alphas": len(seeded_alphas)},
    "ensemble": {"total": n_alphas, "corr_threshold": 0.5, "fdr_q": 0.10},
    "metrics": {k: float(v) for k, v in metrics.items()},
    "walk_forward": wf_results,
    "alphas": [{"expr": a.expression[:80], "ic": a.test_ic, "hit": a.hit_rate} for a in final_alphas],
}
summary["metrics"]["calmar"] = float(calmar)
with open(results_dir / 'backtest_v23_results.json', 'w') as f:
    json.dump(summary, f, indent=2, default=str)
bt_result.equity_curve.to_csv(results_dir / 'equity_curve.csv')
logger.info("Saved to data/backtest_v23_results/")
