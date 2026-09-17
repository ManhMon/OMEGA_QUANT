"""
Dynamic Universe PnL Attribution Analysis Script
Role 14 - Data Scientist L2 Analysis
Gate: DYNAMIC_UNIVERSE_PNL_ATTRIBUTION_20260615
"""
import json
import statistics
import math

# Load data
with open(r"C:\Users\GHC\repos\OMEGA_QUANT\data\phase35_results\phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json", "r") as f:
    data = json.load(f)

folds = data["fold_details"]
summary = data["summary"]
config = data["config"]

# ============================================================
# 1. FOLD-LEVEL PnL ANALYSIS
# ============================================================
print("=" * 80)
print("1. FOLD-LEVEL PnL ANALYSIS")
print("=" * 80)

pnl_values = [f["portfolio_pnl_vnd"] for f in folds]
total_return_values = [f["portfolio_total_return"] for f in folds]
ic_values = [f["portfolio_ic"] for f in folds]
sharpe_values = [f["portfolio_sharpe"] for f in folds]
max_dd_values = [f["portfolio_max_dd"] for f in folds]

total_pnl = sum(pnl_values)
mean_pnl = statistics.mean(pnl_values)
median_pnl = statistics.median(pnl_values)
std_pnl = statistics.stdev(pnl_values) if len(pnl_values) > 1 else 0

print(f"Total PnL (sum of folds): {total_pnl:,.0f} VND")
print(f"Mean PnL per fold:        {mean_pnl:,.0f} VND")
print(f"Median PnL per fold:      {median_pnl:,.0f} VND")
print(f"Std PnL:                  {std_pnl:,.0f} VND")
print(f"Mean vs Median ratio:     {mean_pnl/median_pnl:.2f}x")
print()

# Sorted PnL by magnitude
print("\nFold PnL sorted by magnitude:")
for f in sorted(folds, key=lambda x: x["portfolio_pnl_vnd"], reverse=True):
    pct_of_total = (f["portfolio_pnl_vnd"] / total_pnl) * 100 if total_pnl != 0 else 0
    print(f"  Fold {f['fold_id']:2d}: {f['portfolio_pnl_vnd']:>16,.0f} VND  ({pct_of_total:+6.1f}% of total)  "
          f"IC={f['portfolio_ic']:+.4f}  Sharpe={f['portfolio_sharpe']:+.2f}  "
          f"Period: {f['test_start'][:4]}-{f['test_end'][:4]}")

# ============================================================
# 2. PnL CONCENTRATION
# ============================================================
print("\n" + "=" * 80)
print("2. PnL CONCENTRATION")
print("=" * 80)

# Only positive PnL folds for concentration
positive_pnl = sorted([f["portfolio_pnl_vnd"] for f in folds if f["portfolio_pnl_vnd"] > 0], reverse=True)
positive_total = sum(positive_pnl)

if positive_total > 0:
    top1_share = positive_pnl[0] / positive_total * 100
    top3_share = sum(positive_pnl[:3]) / positive_total * 100
    top5_share = sum(positive_pnl[:5]) / positive_total * 100
else:
    top1_share = top3_share = top5_share = 0

print(f"Positive PnL folds: {len(positive_pnl)} of {len(pnl_values)}")
print(f"Negative PnL folds: {len(pnl_values) - len(positive_pnl)} of {len(pnl_values)}")
print(f"Top-1 positive fold share: {top1_share:.1f}%")
print(f"Top-3 positive folds share: {top3_share:.1f}%")
print(f"Top-5 positive folds share: {top5_share:.1f}%")

# Overall concentration including negatives
abs_pnl_sorted = sorted([abs(p) for p in pnl_values], reverse=True)
top1_overall_share = abs_pnl_sorted[0] / sum(abs_pnl_sorted) * 100
top3_overall_share = sum(abs_pnl_sorted[:3]) / sum(abs_pnl_sorted) * 100
print(f"\nAbsolute PnL concentration (all folds):")
print(f"  Top-1 abs share: {top1_overall_share:.1f}%")
print(f"  Top-3 abs share: {top3_overall_share:.1f}%")

# ============================================================
# 3. FOLD 6 OUTLIER IMPACT
# ============================================================
print("\n" + "=" * 80)
print("3. FOLD 6 OUTLIER IMPACT ANALYSIS")
print("=" * 80)

fold6 = [f for f in folds if f["fold_id"] == 6][0]
fold6_pnl = fold6["portfolio_pnl_vnd"]
fold6_share = (fold6_pnl / total_pnl) * 100
pnl_excl_fold6 = total_pnl - fold6_pnl
mean_excl_fold6 = statistics.mean([f["portfolio_pnl_vnd"] for f in folds if f["fold_id"] != 6])
median_excl_fold6 = statistics.median([f["portfolio_pnl_vnd"] for f in folds if f["fold_id"] != 6])
ic_excl_fold6 = statistics.mean([f["portfolio_ic"] for f in folds if f["fold_id"] != 6])
sharpe_excl_fold6 = statistics.mean([f["portfolio_sharpe"] for f in folds if f["fold_id"] != 6])

print(f"Fold 6 PnL:           {fold6_pnl:,.0f} VND ({fold6_share:.1f}% of total)")
print(f"Fold 6 IC:            {fold6['portfolio_ic']:.4f} (avg={summary['avg_portfolio_ic']:.4f})")
print(f"Fold 6 Sharpe:        {fold6['portfolio_sharpe']:.2f} (avg={summary['avg_portfolio_sharpe']:.2f})")
print(f"Fold 6 Return:        {fold6['portfolio_total_return']*100:.1f}%")
print(f"Fold 6 Max DD:        {fold6['portfolio_max_dd']*100:.1f}%")
print(f"\n--- Excluding Fold 6 ---")
print(f"Total PnL (excl F6):  {pnl_excl_fold6:,.0f} VND")
print(f"Mean PnL (excl F6):   {mean_excl_fold6:,.0f} VND")
print(f"Median PnL (excl F6): {median_excl_fold6:,.0f} VND")
print(f"Mean IC (excl F6):    {ic_excl_fold6:.4f}")
print(f"Mean Sharpe (excl F6):{sharpe_excl_fold6:.2f}")

# ============================================================
# 4. IC / SHARPE / PnL RELATIONSHIP
# ============================================================
print("\n" + "=" * 80)
print("4. IC / SHARPE / PnL RELATIONSHIP")
print("=" * 80)

# Simple correlation between IC and PnL
def pearson_corr(x, y):
    n = len(x)
    mx, my = statistics.mean(x), statistics.mean(y)
    sx, sy = statistics.stdev(x), statistics.stdev(y)
    if sx == 0 or sy == 0:
        return 0
    cov = sum((x[i]-mx)*(y[i]-my) for i in range(n)) / (n-1)
    return cov / (sx * sy)

ic_pnl_corr = pearson_corr(ic_values, pnl_values)
ic_sharpe_corr = pearson_corr(ic_values, sharpe_values)
sharpe_pnl_corr = pearson_corr(sharpe_values, pnl_values)
ic_dd_corr = pearson_corr(ic_values, [abs(d) for d in max_dd_values])

print(f"Correlation IC vs PnL:      {ic_pnl_corr:+.3f}")
print(f"Correlation IC vs Sharpe:   {ic_sharpe_corr:+.3f}")
print(f"Correlation Sharpe vs PnL:  {sharpe_pnl_corr:+.3f}")
print(f"Correlation IC vs |MaxDD|:  {ic_dd_corr:+.3f}")

print("\nFold-level IC/Sharpe/PnL table:")
print(f"{'Fold':>4} {'IC':>8} {'Sharpe':>8} {'PnL(B VND)':>12} {'Return%':>8} {'MaxDD%':>8}")
for f in folds:
    print(f"{f['fold_id']:>4} {f['portfolio_ic']:>8.4f} {f['portfolio_sharpe']:>8.2f} "
          f"{f['portfolio_pnl_vnd']/1e9:>12.2f} {f['portfolio_total_return']*100:>8.1f} "
          f"{f['portfolio_max_dd']*100:>8.1f}")

# ============================================================
# 5. ALPHA SELECTION / WINNER GUARD PATTERNS
# ============================================================
print("\n" + "=" * 80)
print("5. ALPHA SELECTION / WINNER GUARD PATTERNS BY FOLD")
print("=" * 80)

for f in folds:
    wg = f["winner_guard_evidence"]
    pre = wg["pre_guard_alphas"]
    post = wg["post_guard_alphas"]
    excl = wg["excluded_alphas"]
    fb = wg["fallback_used"]
    print(f"\nFold {f['fold_id']:2d}:")
    print(f"  Pre-guard alphas:  {len(pre)} -> {', '.join([a.split('_')[-1] for a in pre])}")
    print(f"  Post-guard alphas: {len(post)} -> {', '.join([a.split('_')[-1] for a in post]) if post else 'NONE'}")
    print(f"  Excluded:          {len(excl)} -> {', '.join([a.split('_')[-1] for a in excl])}")
    print(f"  Fallback used:     {fb}")

# Winner guard statistics
fallback_count = sum(1 for f in folds if f["winner_guard_evidence"]["fallback_used"])
print(f"\n--- Winner Guard Summary ---")
print(f"Fallback used: {fallback_count}/{len(folds)} folds ({fallback_count/len(folds)*100:.0f}%)")

# Most common post-guard alphas
from collections import Counter
post_guard_counter = Counter()
for f in folds:
    for a in f["winner_guard_evidence"]["post_guard_alphas"]:
        post_guard_counter[a] += 1
print(f"\nPost-guard alpha frequency:")
for alpha, count in post_guard_counter.most_common():
    short = alpha.replace("alpha_", "").replace("fml", "F").replace("p34_", "P34_")
    print(f"  {short}: {count}/{len(folds)} folds ({count/len(folds)*100:.0f}%)")

# ============================================================
# 6. DYNAMIC UNIVERSE EVIDENCE BY FOLD
# ============================================================
print("\n" + "=" * 80)
print("6. DYNAMIC UNIVERSE EVIDENCE BY FOLD")
print("=" * 80)

for f in folds:
    du = f["dynamic_universe_evidence"]
    print(f"Fold {f['fold_id']:2d}: enabled={du['enabled']}, schedule_size={du['schedule_size']}, "
          f"exact_entries={du['n_test_dates_with_exact_entry']}, "
          f"carry_forward={du['n_test_dates_with_carry_forward']}, "
          f"rebalances={len(du['rebalance_dates_in_fold'])}")

# ============================================================
# 7. ROBUSTNESS METRICS
# ============================================================
print("\n" + "=" * 80)
print("7. ROBUSTNESS METRICS")
print("=" * 80)

win_rate = sum(1 for p in pnl_values if p > 0) / len(pnl_values) * 100
positive_ic_rate = sum(1 for ic in ic_values if ic > 0) / len(ic_values) * 100
positive_return_rate = sum(1 for r in total_return_values if r > 0) / len(total_return_values) * 100
median_sharpe = statistics.median(sharpe_values)
median_ic = statistics.median(ic_values)
median_max_dd = statistics.median(max_dd_values)
max_negative_fold = min(pnl_values)
min_sharpe = min(sharpe_values)
max_sharpe = max(sharpe_values)

print(f"Median PnL:                {median_pnl:,.0f} VND")
print(f"Median Return:             {statistics.median(total_return_values)*100:.1f}%")
print(f"Median Sharpe:             {median_sharpe:.2f}")
print(f"Median IC:                 {median_ic:.4f}")
print(f"Median Max DD:             {median_max_dd*100:.1f}%")
print(f"Win Rate (positive PnL):   {win_rate:.0f}% ({sum(1 for p in pnl_values if p > 0)}/{len(pnl_values)})")
print(f"Positive IC Fold Rate:     {positive_ic_rate:.0f}% ({sum(1 for ic in ic_values if ic > 0)}/{len(ic_values)})")
print(f"Positive Return Rate:      {positive_return_rate:.0f}% ({sum(1 for r in total_return_values if r > 0)}/{len(total_return_values)})")
print(f"PnL Concentration Top-1:   {top1_share:.1f}% (positive folds)")
print(f"PnL Concentration Top-3:   {top3_share:.1f}% (positive folds)")
print(f"Sharpe Range:              [{min_sharpe:.2f}, {max_sharpe:.2f}]")
print(f"Max Negative Fold PnL:     {max_negative_fold:,.0f} VND")
print(f"Negative folds count:      {sum(1 for p in pnl_values if p < 0)}")

# Sharpe > 0 count
sharpe_positive = sum(1 for s in sharpe_values if s > 0)
print(f"Sharpe > 0 rate:           {sharpe_positive}/{len(sharpe_values)} ({sharpe_positive/len(sharpe_values)*100:.0f}%)")

# ============================================================
# 8. HEADLINE COMPARISON: DYNAMIC vs ROLLING vs STATIC
# ============================================================
print("\n" + "=" * 80)
print("8. HEADLINE COMPARISON: DYNAMIC vs ROLLING vs STATIC")
print("=" * 80)

# Load rolling and static summaries
with open(r"C:\Users\GHC\repos\OMEGA_QUANT\data\phase35_results\phase35_backtest_results_rolling_universe_best_config_20260615_baseline.json", "r") as f:
    rolling = json.load(f)
with open(r"C:\Users\GHC\repos\OMEGA_QUANT\data\phase35_results\phase35_backtest_results_cpcv12_v3_winner_guard_baseline.json", "r") as f:
    static = json.load(f)

print(f"\n{'Metric':<25} {'Dynamic':>15} {'Rolling':>15} {'Static(WG)':>15}")
print("-" * 70)

ds, rs, ss = summary, rolling["summary"], static["summary"]
print(f"{'Avg IC':<25} {ds['avg_portfolio_ic']:>15.4f} {rs['avg_portfolio_ic']:>15.4f} {ss['avg_portfolio_ic']:>15.4f}")
print(f"{'Avg Sharpe':<25} {ds['avg_portfolio_sharpe']:>15.2f} {rs['avg_portfolio_sharpe']:>15.2f} {ss['avg_portfolio_sharpe']:>15.2f}")
print(f"{'Avg Max DD':<25} {ds['avg_portfolio_max_dd']*100:>14.1f}% {rs['avg_portfolio_max_dd']*100:>14.1f}% {ss['avg_portfolio_max_dd']*100:>14.1f}%")
print(f"{'Avg PnL (M VND)':<25} {ds['avg_portfolio_pnl_vnd']/1e6:>15.0f} {rs['avg_portfolio_pnl_vnd']/1e6:>15.0f} {ss['avg_portfolio_pnl_vnd']/1e6:>15.0f}")
print(f"{'Total Folds':<25} {ds['total_folds']:>15} {rs['total_folds']:>15} {ss['total_folds']:>15}")

# Dynamic universe config comparison
print(f"\nConfig differences:")
dc = config
rc = rolling["config"]
print(f"  Dynamic universe enabled: {dc.get('dynamic_universe_enabled', 'N/A')}")
print(f"  Rolling universe enabled: {rc.get('rolling_universe_enabled', 'N/A')}")
print(f"  Dynamic lookback days: {dc.get('dynamic_universe_lookback_days', 'N/A')}")
print(f"  Dynamic rebalance days: {dc.get('dynamic_universe_rebalance_days', 'N/A')}")
print(f"  Dynamic top N: {dc.get('dynamic_universe_top_n', 'N/A')}")

# ============================================================
# 9. SYMBOL/DATE/SECTOR CONTRIBUTION
# ============================================================
print("\n" + "=" * 80)
print("9. SYMBOL/DATE/SECTOR CONTRIBUTION")
print("=" * 80)

# Check if symbol-level contribution is in the JSON
has_symbol_data = False
du_evidence = data.get("dynamic_universe_evidence", [])
if du_evidence:
    print(f"Dynamic universe evidence entries: {len(du_evidence)}")
    # Extract all unique symbols
    all_symbols = set()
    for entry in du_evidence[:5]:  # First 5 entries
        all_symbols.update(entry.get("selected_symbols", []))
    print(f"Sample symbols from first 5 rebalances: {sorted(all_symbols)}")
    
    # Universe size evolution
    sizes = [(e["rebalance_date"], e["n_selected"]) for e in du_evidence]
    print(f"\nUniverse size evolution (first 10 rebalances):")
    for date, size in sizes[:10]:
        print(f"  {date}: {size} symbols selected")
    print(f"  ... ({len(sizes)} total rebalances)")
    print(f"  Min universe size: {min(s for _, s in sizes)}")
    print(f"  Max universe size: {max(s for _, s in sizes)}")
    print(f"  Mean universe size: {statistics.mean(s for _, s in sizes):.1f}")
    
    # Turnover
    turnovers = [e.get("turnover_from_previous") for e in du_evidence if e.get("turnover_from_previous") is not None]
    if turnovers:
        print(f"\nUniverse turnover:")
        print(f"  Mean turnover: {statistics.mean(turnovers)*100:.1f}%")
        print(f"  Median turnover: {statistics.median(turnovers)*100:.1f}%")
        print(f"  Max turnover: {max(turnovers)*100:.1f}%")
        zero_turnover = sum(1 for t in turnovers if t == 0)
        print(f"  Zero turnover rebalances: {zero_turnover}/{len(turnovers)} ({zero_turnover/len(turnovers)*100:.0f}%)")
else:
    print("No dynamic universe evidence at top level")

print("\n--- SYMBOL/DATE/SECTOR PER-FOLD CONTRIBUTION ---")
print("UNAVAILABLE: The JSON does not contain per-symbol, per-date, or per-sector")
print("PnL contribution breakdown. Only fold-level aggregate metrics are available.")
print("RECOMMENDATION: Instrument per-symbol PnL tracking in backtest engine for")
print("future attribution analysis. Add sector mapping to fold_details output.")

# ============================================================
# 10. PnL PERIOD INTERPRETATION
# ============================================================
print("\n" + "=" * 80)
print("10. PnL PERIOD INTERPRETATION")
print("=" * 80)

print(f"\nBacktest span: {config['start_date']} to {config['end_date']}")
print(f"Train: {config['train_years']} years expanding window")
print(f"Test: {config['test_years']} year per fold")
print(f"Folds: {config['n_folds_executed']} executed of {config['n_folds']} requested")
print(f"Initial capital: {config['initial_capital']/1e9:.1f}B VND")
print(f"Strategy: {config['strategy']}")
print(f"Slippage: {config['slippage_bps']} bps, Commission: {config['commission_bps']} bps")
print(f"Drawdown control: {config['drawdown_control']} (threshold: {config['drawdown_threshold']})")
print(f"Return horizon: {config['return_horizon']} days")
print(f"Stage 2: top {config['stage2_top_n_stocks']} stocks, rebalance every {config['stage2_rebalance_freq']} days, sector cap {config['stage2_sector_cap_pct']*100:.0f}%")

# Period interpretation
print("\n--- Period Context ---")
periods = [
    ("Fold 1", "2018-2019", "VN-Index correction after 2018 peak, trade war onset"),
    ("Fold 2", "2018-2019", "Late 2018 sell-off, 2019 sideways recovery"),
    ("Fold 3", "2019-2020", "Low-vol sideways, then COVID crash Mar 2020"),
    ("Fold 4", "2020-2021", "COVID recovery, massive VN retail boom"),
    ("Fold 5", "2020-2021", "Bull market continuation, new retail investor wave"),
    ("Fold 6", "2021-2022", "Peak VN-Index bull run (1500+), then correction"),
    ("Fold 7", "2022-2023", "VN-Index correction, real estate bond crisis"),
    ("Fold 8", "2022-2023", "Bear market, regulatory crackdown"),
    ("Fold 9", "2023-2024", "Recovery phase, FDI inflow, KRX system"),
    ("Fold 10", "2024-2025", "Market stabilization, upgrade anticipation"),
    ("Fold 11", "2024-2025", "Frontier to emerging market upgrade narrative"),
    ("Fold 12", "2025-2026", "Most recent period, upgrade realization"),
]
for fold_name, period, context in periods:
    print(f"  {fold_name} ({period}): {context}")

print("\n\nAnalysis complete.")
