"""Quick diagnostic script to analyze existing per-fold CPCV artifacts.

Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621
Read-only: does NOT modify any strategy/risk/overlay logic.

Formula
-------
gross_return (%) = net_return (%) + total_cost (%)

where:
  net_return = total_return * 100  (compound post-cost return, from JSON)
  total_cost = cost_breakdown["total_cost"] * 100
             = (total_commission_cost + total_spread_cost + total_slippage_cost) * 100

This is an ADDITIVE APPROXIMATION to the true compound gross return.
The exact gross would require adding back costs per-bar before compounding.
Source: apply_realistic_tc() in src/omega/quant/execution_sim.py, line 871:
  "total_cost": float(total_commission + total_spread + total_slippage)
"""
import json, os, glob
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results_dir = os.path.join(REPO_ROOT, "data", "phase35_results")

hybrid_folds = {}
baseline_folds = {}

for f in glob.glob(os.path.join(results_dir, "hybrid_fold*_Hybrid_full_evidence_20260621_1335.json")):
    bn = os.path.basename(f)
    fold_id = int(bn.split("_Hybrid")[0].replace("hybrid_fold", ""))
    with open(f) as fh:
        data = json.load(fh)
    hybrid_folds[fold_id] = data

for f in glob.glob(os.path.join(results_dir, "hybrid_fold*_Baseline_full_evidence_20260621_1335.json")):
    bn = os.path.basename(f)
    fold_id = int(bn.split("_Baseline")[0].replace("hybrid_fold", ""))
    with open(f) as fh:
        data = json.load(fh)
    baseline_folds[fold_id] = data

n_hybrid = len(hybrid_folds)
n_baseline = len(baseline_folds)
print(f"Found {n_hybrid} Hybrid folds, {n_baseline} Baseline folds")

# Compute diagnostic metrics for each fold
hdr = f"{'Fold':>4} | {'Net Ret%':>8} | {'TC%':>8} | {'Gross Ret%':>10} | {'Turnover':>10} | {'Avg TO/bar':>10} | {'Cost/bar bps':>12} | {'N Days':>6} | {'MaxDD%':>8}"
print()
print("=" * len(hdr))
print(hdr)
print("-" * len(hdr))

gross_returns = []
tc_pcts = []
net_returns = []
turnovers = []
avg_turnovers = []
n_days_list = []
cash_end_folds = 0

for fid in sorted(hybrid_folds.keys()):
    d = hybrid_folds[fid]
    net_ret = d["total_return"] * 100
    cb = d["cost_breakdown"]
    tc_pct = cb["total_cost"] * 100
    gross_ret = net_ret + tc_pct
    turnover = cb["total_turnover"]
    avg_to = cb["avg_turnover_per_bar"]
    cost_per_bar = cb["avg_cost_per_bar_bps"]
    n_days = d["n_days"]
    max_dd = d["max_drawdown"] * 100

    gross_returns.append(gross_ret)
    tc_pcts.append(tc_pct)
    net_returns.append(net_ret)
    turnovers.append(turnover)
    avg_turnovers.append(avg_to)
    n_days_list.append(n_days)

    # Cash proxy: if final_w is all zeros, last day was in cooldown
    fw = cb.get("final_w", "")
    if "0. 0. 0." in str(fw):
        cash_end_folds += 1

    print(f"{fid:>4} | {net_ret:>+8.2f} | {tc_pct:>8.2f} | {gross_ret:>+10.2f} | {turnover:>10.2f} | {avg_to:>10.4f} | {cost_per_bar:>12.4f} | {n_days:>6} | {max_dd:>8.2f}")

print("-" * len(hdr))
print(f"Mean | {np.mean(net_returns):>+8.2f} | {np.mean(tc_pcts):>8.2f} | {np.mean(gross_returns):>+10.2f} | {np.mean(turnovers):>10.2f} | {np.mean(avg_turnovers):>10.4f} |")
print(f"Med  | {np.median(net_returns):>+8.2f} | {np.median(tc_pcts):>8.2f} | {np.median(gross_returns):>+10.2f} | {np.median(turnovers):>10.2f} | {np.median(avg_turnovers):>10.4f} |")
print(f"Min  | {np.min(net_returns):>+8.2f} | {np.min(tc_pcts):>8.2f} | {np.min(gross_returns):>+10.2f} | {np.min(turnovers):>10.2f} |")
print(f"Max  | {np.max(net_returns):>+8.2f} | {np.max(tc_pcts):>8.2f} | {np.max(gross_returns):>+10.2f} | {np.max(turnovers):>10.2f} |")

# Key analysis
print()
print("=" * 60)
print("ROOT CAUSE ANALYSIS")
print("=" * 60)

n_gross_positive = sum(1 for g in gross_returns if g > 0)
n_gross_negative = sum(1 for g in gross_returns if g <= 0)
print(f"(a) Folds with GROSS return > 0:  {n_gross_positive}/{n_hybrid} ({n_gross_positive/n_hybrid*100:.1f}%)" if n_hybrid > 0 else "(a) No hybrid folds found")
print(f"(a) Folds with GROSS return <= 0: {n_gross_negative}/{n_hybrid} ({n_gross_negative/n_hybrid*100:.1f}%)" if n_hybrid > 0 else "")

tc_exceeds_count = 0
for i in range(len(gross_returns)):
    if gross_returns[i] > 0 and tc_pcts[i] > gross_returns[i]:
        tc_exceeds_count += 1
print(f"(a) Folds where gross > 0 but TC > gross: {tc_exceeds_count}/{n_gross_positive}" if n_gross_positive > 0 else "(a) No folds with positive gross")

print(f"(b/d) Folds ending in cash (final_w all zero): {cash_end_folds}/{n_hybrid} ({cash_end_folds/n_hybrid*100:.1f}%)" if n_hybrid > 0 else "")

high_to_folds = sum(1 for t in avg_turnovers if t > 0.1)
print(f"    Folds with avg_turnover/bar > 0.10 (high churn): {high_to_folds}/{n_hybrid}")

# Compare Baseline
if baseline_folds:
    bl_net = [baseline_folds[fid]["total_return"] * 100 for fid in sorted(baseline_folds.keys())]
    bl_cb = [baseline_folds[fid]["cost_breakdown"]["total_cost"] * 100 for fid in sorted(baseline_folds.keys())]
    bl_gross = [n + c for n, c in zip(bl_net, bl_cb)]
    bl_to = [baseline_folds[fid]["cost_breakdown"]["total_turnover"] for fid in sorted(baseline_folds.keys())]
    print()
    print("=" * 60)
    print("BASELINE vs HYBRID COMPARISON")
    print("=" * 60)
    print(f"BASELINE: mean_net={np.mean(bl_net):+.2f}%  mean_TC={np.mean(bl_cb):.2f}%  mean_gross={np.mean(bl_gross):+.2f}%  mean_to={np.mean(bl_to):.1f}")
    print(f"HYBRID:   mean_net={np.mean(net_returns):+.2f}%  mean_TC={np.mean(tc_pcts):.2f}%  mean_gross={np.mean(gross_returns):+.2f}%  mean_to={np.mean(turnovers):.1f}")
    delta_net = np.mean(net_returns) - np.mean(bl_net)
    delta_tc = np.mean(tc_pcts) - np.mean(bl_cb)
    delta_gross = np.mean(gross_returns) - np.mean(bl_gross)
    delta_to = np.mean(turnovers) - np.mean(bl_to)
    print(f"DELTA:    net={delta_net:+.2f}%  TC={delta_tc:+.2f}%  gross={delta_gross:+.2f}%  turnover={delta_to:+.1f}")

# Turnover distribution
print()
print("=" * 60)
print("TURNOVER DISTRIBUTION")
print("=" * 60)
for pct in [10, 25, 50, 75, 90]:
    val = np.percentile(turnovers, pct)
    print(f"  P{pct:02d}: {val:.2f}")

# Cost breakdown composition
print()
print("=" * 60)
print("COST BREAKDOWN COMPOSITION (mean across folds)")
print("=" * 60)
comm = []
spread = []
slip = []
for fid in sorted(hybrid_folds.keys()):
    cb = hybrid_folds[fid]["cost_breakdown"]
    comm.append(cb["total_commission_cost"] * 100)
    spread.append(cb["total_spread_cost"] * 100)
    slip.append(cb["total_slippage_cost"] * 100)
print(f"  Commission: {np.mean(comm):.2f}%  (range {np.min(comm):.2f} - {np.max(comm):.2f})")
print(f"  Spread:     {np.mean(spread):.2f}%  (range {np.min(spread):.2f} - {np.max(spread):.2f})")
print(f"  Slippage:   {np.mean(slip):.2f}%  (range {np.min(slip):.2f} - {np.max(slip):.2f})")
print(f"  TOTAL:      {np.mean(tc_pcts):.2f}%")

# Verify total_cost = commission + spread + slippage
print()
print("=" * 60)
print("FORMULA VERIFICATION")
print("=" * 60)
print("total_cost = commission + spread + slippage (from execution_sim.py line 871)")
for fid in sorted(hybrid_folds.keys())[:3]:
    cb = hybrid_folds[fid]["cost_breakdown"]
    computed = cb["total_commission_cost"] + cb["total_spread_cost"] + cb["total_slippage_cost"]
    reported = cb["total_cost"]
    match = "MATCH" if abs(computed - reported) < 1e-10 else "MISMATCH"
    print(f"  Fold {fid}: computed={computed*100:.4f}%, reported={reported*100:.4f}% [{match}]")

# Alpha IC per regime (from profitability_diag if present in JSONs)
print()
print("=" * 60)
print("ALPHA IC PER REGIME (from per-fold profitability_diag)")
print("=" * 60)
ic_bull_all = []
ic_side_all = []
ic_bear_all = []
ic_overall_all = []
n_with_diag = 0
for fid in sorted(hybrid_folds.keys()):
    d = hybrid_folds[fid]
    pd_diag = d.get("profitability_diag", {})
    if pd_diag:
        n_with_diag += 1
        ic_ov = pd_diag.get("alpha_ic_overall", float("nan"))
        if isinstance(ic_ov, (int, float)) and not (isinstance(ic_ov, float) and np.isnan(ic_ov)):
            ic_overall_all.append(ic_ov)
        ic_regime = pd_diag.get("alpha_ic_per_regime", {})
        if isinstance(ic_regime, dict):
            for rk, arr in [("bull", ic_bull_all), ("sideways", ic_side_all), ("bear", ic_bear_all)]:
                v = ic_regime.get(rk, float("nan"))
                if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
                    arr.append(v)

if n_with_diag > 0:
    print(f"  Folds with profitability_diag: {n_with_diag}/{n_hybrid}")
    if ic_overall_all:
        print(f"  IC overall: mean={np.mean(ic_overall_all):+.4f}, std={np.std(ic_overall_all):.4f}, n={len(ic_overall_all)}")
    if ic_bull_all:
        print(f"  IC bull:    mean={np.mean(ic_bull_all):+.4f}, std={np.std(ic_bull_all):.4f}, n={len(ic_bull_all)}")
    if ic_side_all:
        print(f"  IC sideways:mean={np.mean(ic_side_all):+.4f}, std={np.std(ic_side_all):.4f}, n={len(ic_side_all)}")
    if ic_bear_all:
        print(f"  IC bear:    mean={np.mean(ic_bear_all):+.4f}, std={np.std(ic_bear_all):.4f}, n={len(ic_bear_all)}")
else:
    print("  No per-fold profitability_diag found (run backtest with diagnostic handler first)")
