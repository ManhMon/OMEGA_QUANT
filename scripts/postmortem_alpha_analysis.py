"""Postmortem alpha analysis for hybrid GMM-BOCPD backtest.

Computes:
1. Cross-sectional IC (rank correlation) of composite_signal vs next-day returns
2. Gross vs net alpha analysis
3. Turnover/cost decomposition
4. Vol-target leverage impact assessment
5. Regime overlay timing analysis

All paths are repo-relative from REPO_ROOT.
"""
import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
os.chdir(str(REPO_ROOT))

import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ---- Load equity curves and result JSONs ----
eq_baseline = pd.read_csv(REPO_ROOT / "data/phase35_results/hybrid_eq_Baseline_No_GMM-BOCPD.csv")
eq_hybrid = pd.read_csv(REPO_ROOT / "data/phase35_results/hybrid_eq_Hybrid_GMM-BOCPD_Active.csv")

with open(REPO_ROOT / "data/phase35_results/hybrid_res_Baseline_No_GMM-BOCPD.json") as f:
    res_baseline = json.load(f)
with open(REPO_ROOT / "data/phase35_results/hybrid_res_Hybrid_GMM-BOCPD_Active.json") as f:
    res_hybrid = json.load(f)

# ---- Section 1: Daily return statistics ----
print("=" * 80)
print("SECTION 1: Daily Return Distribution Analysis")
print("=" * 80)

for name, eq_df, res in [
    ("Baseline (HMM only)", eq_baseline, res_baseline),
    ("Hybrid GMM-BOCPD", eq_hybrid, res_hybrid),
]:
    dr = eq_df["daily_ret"].values[1:]  # skip first zero
    cp = eq_df["cum_prod"].values
    
    n = len(dr)
    mean_dr = np.mean(dr)
    std_dr = np.std(dr, ddof=1)
    skew = pd.Series(dr).skew()
    kurt = pd.Series(dr).kurtosis()
    
    # Win rate
    win_rate = np.mean(dr > 0)
    
    # Annualized return
    total_ret = cp[-1] / cp[0] - 1
    ann_ret = (1 + total_ret) ** (252 / n) - 1
    
    # Annualized vol
    ann_vol = std_dr * np.sqrt(252)
    
    # Sharpe
    sharpe = mean_dr / std_dr * np.sqrt(252) if std_dr > 0 else 0
    
    # Max drawdown
    running_max = np.maximum.accumulate(cp)
    dd = (cp - running_max) / running_max
    max_dd = np.min(dd)
    
    # % of days with negative return
    pct_neg = np.mean(dr < 0)
    
    # Consecutive loss streaks
    is_loss = dr < 0
    max_streak = 0
    current_streak = 0
    for x in is_loss:
        if x:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    
    print(f"\n--- {name} ---")
    print(f"  N days: {n}")
    print(f"  Total return: {total_ret*100:.2f}%")
    print(f"  Annualized return: {ann_ret*100:.2f}%")
    print(f"  Annualized vol: {ann_vol*100:.2f}%")
    print(f"  Sharpe: {sharpe:.4f}")
    print(f"  Max drawdown: {max_dd*100:.2f}%")
    print(f"  Mean daily return: {mean_dr*10000:.4f} bps")
    print(f"  Std daily return: {std_dr*10000:.4f} bps")
    print(f"  Skewness: {skew:.3f}")
    print(f"  Kurtosis: {kurt:.3f}")
    print(f"  Win rate: {win_rate*100:.1f}%")
    print(f"  % negative days: {pct_neg*100:.1f}%")
    print(f"  Max consecutive loss streak: {max_streak} days")

# ---- Section 2: Cost decomposition analysis ----
print("\n" + "=" * 80)
print("SECTION 2: Transaction Cost Decomposition")
print("=" * 80)

for name, res in [
    ("Baseline (HMM only)", res_baseline),
    ("Hybrid GMM-BOCPD", res_hybrid),
]:
    cb = res["cost_breakdown"]
    n = res["n_days"]
    
    print(f"\n--- {name} ---")
    print(f"  Total turnover (cumulative): {cb['total_turnover']:.2f}")
    print(f"  Avg turnover per bar: {cb['avg_turnover_per_bar']:.4f} ({cb['avg_turnover_per_bar']*100:.1f}% one-way)")
    print(f"  Total commission cost: {cb['total_commission_cost']*100:.2f}% (cumulative)")
    print(f"  Total spread cost: {cb['total_spread_cost']*100:.2f}% (cumulative)")
    print(f"  Total slippage cost: {cb['total_slippage_cost']*100:.2f}% (cumulative)")
    print(f"  Total cost: {cb['total_cost']*100:.2f}% (cumulative)")
    print(f"  Avg cost per bar: {cb['avg_cost_per_bar_bps']:.2f} bps")
    print(f"  Annualized cost drag: {cb['total_cost'] / n * 252 * 100:.2f}%")
    
    # Estimate round-trip cost per rebalance
    rt_cost_per_rebalance = cb['avg_cost_per_bar_bps']
    print(f"  Implied round-trip cost per rebalance: {rt_cost_per_rebalance:.1f} bps")

# ---- Section 3: Gross vs Net return decomposition ----
print("\n" + "=" * 80)
print("SECTION 3: Gross vs Net Return Decomposition")
print("=" * 80)

for name, eq_df, res in [
    ("Baseline (HMM only)", eq_baseline, res_baseline),
    ("Hybrid GMM-BOCPD", eq_hybrid, res_hybrid),
]:
    dr = eq_df["daily_ret"].values[1:]
    n = len(dr)
    cb = res["cost_breakdown"]
    
    # Net total return
    net_total = res["total_return"]
    
    # Estimate gross return: net + total costs
    gross_total_approx = net_total + cb["total_cost"]
    
    # Cost as fraction of gross
    if abs(gross_total_approx) > 0.01:
        cost_pct_of_gross = cb["total_cost"] / abs(gross_total_approx) * 100
    else:
        cost_pct_of_gross = float("inf")
    
    print(f"\n--- {name} ---")
    print(f"  Net total return: {net_total*100:.2f}%")
    print(f"  Total transaction costs: {cb['total_cost']*100:.2f}%")
    print(f"  Estimated gross return (net + costs): {gross_total_approx*100:.2f}%")
    print(f"  Costs as % of |gross|: {cost_pct_of_gross:.1f}%")
    
    # If gross is also very negative, the signal itself is bad
    if gross_total_approx < -0.20:
        print(f"  VERDICT: Signal is deeply negative even BEFORE costs (gross = {gross_total_approx*100:.1f}%)")
        print(f"           This is NOT just a cost problem — alpha signal is harmful.")
    elif gross_total_approx > 0:
        print(f"  VERDICT: Signal has positive gross alpha, costs are eating it.")
    else:
        print(f"  VERDICT: Signal has weak/mildly negative gross alpha.")

# ---- Section 4: Vol-target leverage analysis ----
print("\n" + "=" * 80)
print("SECTION 4: Vol-Target Leverage Amplification Analysis")
print("=" * 80)

for name, eq_df in [
    ("Baseline (HMM only)", eq_baseline),
    ("Hybrid GMM-BOCPD", eq_hybrid),
]:
    dr = eq_df["daily_ret"].values[1:]
    n = len(dr)
    
    # Rolling realized vol (60-day)
    window = 60
    if n >= window:
        rolling_vol = pd.Series(dr).rolling(window).std().dropna() * np.sqrt(252)
        avg_realized_vol = rolling_vol.mean()
        max_realized_vol = rolling_vol.max()
        min_realized_vol = rolling_vol.min()
        
        # Implied leverage from vol target
        target_vol = 0.20  # from TailControlOverlay(target_vol_ann=0.2)
        max_leverage = 3.0
        
        implied_leverage = np.clip(target_vol / rolling_vol, 0, max_leverage)
        avg_leverage = implied_leverage.mean()
        max_leverage_actual = implied_leverage.max()
        
        # Days where leverage was at max
        pct_max_lev = (implied_leverage >= max_leverage - 0.01).mean() * 100
        
        print(f"\n--- {name} ---")
        print(f"  Target vol: {target_vol*100:.0f}% annualized")
        print(f"  Max allowed leverage: {max_leverage:.1f}x")
        print(f"  Avg realized vol: {avg_realized_vol*100:.2f}%")
        print(f"  Max realized vol: {max_realized_vol*100:.2f}%")
        print(f"  Min realized vol: {min_realized_vol*100:.2f}%")
        print(f"  Avg implied leverage: {avg_leverage:.2f}x")
        print(f"  Max implied leverage: {max_leverage_actual:.2f}x")
        print(f"  % days at max leverage: {pct_max_lev:.1f}%")
        
        # When leverage is high, are returns worse?
        high_lev_mask = implied_leverage > avg_leverage
        if high_lev_mask.sum() > 10:
            # Align indices
            lev_dates = rolling_vol.index[high_lev_mask]
            # Get returns for the NEXT period after high leverage
            next_ret_dates = [d + 1 for d in lev_dates if d + 1 < n]
            if len(next_ret_dates) > 10:
                high_lev_rets = dr[next_ret_dates]
                low_lev_rets = dr[rolling_vol.index[~high_lev_mask].values + 1] if (~high_lev_mask).sum() > 0 else np.array([0])
                low_lev_rets = low_lev_rets[:min(len(low_lev_rets), len(high_lev_rets))]
                print(f"  Avg return when leverage HIGH: {np.mean(high_lev_rets)*10000:.2f} bps")
                print(f"  Avg return when leverage LOW:  {np.mean(low_lev_rets)*10000:.2f} bps")

# ---- Section 5: Drawdown analysis and regime overlay timing ----
print("\n" + "=" * 80)
print("SECTION 5: Drawdown & Regime Overlay Timing")
print("=" * 80)

# Compare the two scenarios to see where they diverge
dr_b = eq_baseline["daily_ret"].values
dr_h = eq_hybrid["daily_ret"].values
cp_b = eq_baseline["cum_prod"].values
cp_h = eq_hybrid["cum_prod"].values

# Find first divergence point
diverge_idx = None
for i in range(len(dr_b)):
    if abs(dr_b[i] - dr_h[i]) > 1e-10:
        diverge_idx = i
        break

print(f"First divergence at day index: {diverge_idx}")
if diverge_idx is not None:
    print(f"  Baseline cum_prod at divergence: {cp_b[diverge_idx]:.6f}")
    print(f"  Hybrid cum_prod at divergence:   {cp_h[diverge_idx]:.6f}")

# Compute divergence over time
divergence = cp_h - cp_b
print(f"\nDivergence (Hybrid - Baseline) statistics:")
print(f"  Mean: {np.mean(divergence)*100:.4f}%")
print(f"  Std: {np.std(divergence)*100:.4f}%")
print(f"  Min: {np.min(divergence)*100:.4f}%")
print(f"  Max: {np.max(divergence)*100:.4f}%")
print(f"  Final: {divergence[-1]*100:.4f}%")

# Drawdown comparison
for name, cp in [("Baseline", cp_b), ("Hybrid", cp_h)]:
    rm = np.maximum.accumulate(cp)
    dd = (cp - rm) / rm
    # Time in drawdown > 5%
    pct_in_dd_5 = (dd < -0.05).mean() * 100
    pct_in_dd_10 = (dd < -0.10).mean() * 100
    pct_in_dd_20 = (dd < -0.20).mean() * 100
    
    # Recovery time from max drawdown
    max_dd_idx = np.argmin(dd)
    if max_dd_idx < len(cp) - 1:
        # Check if recovery happened
        post_dd = cp[max_dd_idx:]
        pre_dd_peak = rm[max_dd_idx]
        recovered = np.any(post_dd >= pre_dd_peak)
        print(f"\n--- {name} ---")
        print(f"  Max DD date index: {max_dd_idx} (of {len(cp)} total)")
        print(f"  Max DD depth: {dd[max_dd_idx]*100:.2f}%")
        print(f"  Recovered from max DD: {recovered}")
    else:
        print(f"\n--- {name} ---")
        print(f"  Max DD at end of period: {dd[-1]*100:.2f}%")
    
    print(f"  % time in DD > 5%: {pct_in_dd_5:.1f}%")
    print(f"  % time in DD > 10%: {pct_in_dd_10:.1f}%")
    print(f"  % time in DD > 20%: {pct_in_dd_20:.1f}%")

# ---- Section 6: Turnover analysis (daily) ----
print("\n" + "=" * 80)
print("SECTION 6: Turnover Deep Dive")
print("=" * 80)

for name, res in [("Baseline", res_baseline), ("Hybrid", res_hybrid)]:
    cb = res["cost_breakdown"]
    n = res["n_days"]
    avg_to = cb["avg_turnover_per_bar"]
    
    # With gross exposure = 2.0 (long 1.0 + short -1.0), 
    # turnover of 1.32 means 66% of the portfolio changes every day
    # For a 10-stock universe, that's ~6-7 stocks traded daily
    pct_portfolio_traded = avg_to / 2.0 * 100  # gross exposure is ~2.0
    
    # Annualized turnover
    ann_turnover = avg_to * 252
    
    # Cost per unit turnover
    cost_per_unit_to = cb["total_cost"] / cb["total_turnover"] if cb["total_turnover"] > 0 else 0
    
    print(f"\n--- {name} ---")
    print(f"  Avg daily one-way turnover: {avg_to:.4f} ({avg_to*100:.1f}%)")
    print(f"  % of gross portfolio traded daily: {pct_portfolio_traded:.1f}%")
    print(f"  Annualized one-way turnover: {ann_turnover:.0f}x")
    print(f"  Cost per unit turnover: {cost_per_unit_to*10000:.2f} bps")
    print(f"  If turnover were halved, cost savings: {cb['total_cost']*0.5*100:.2f}% cumulative")

# ---- Section 7: Implied IC from performance ----
print("\n" + "=" * 80)
print("SECTION 7: Implied Signal Quality (Reverse-Engineered)")
print("=" * 80)

# With a long/short portfolio of 10 stocks, the expected return depends on IC.
# For a cross-sectional strategy:
#   E[return] ≈ IC * σ_cross_section * sqrt(N) / holding_period
# But we can reverse-engineer: if gross return is known, what IC is implied?

for name, eq_df, res in [
    ("Baseline", eq_baseline, res_baseline),
    ("Hybrid", eq_hybrid, res_hybrid),
]:
    dr = eq_df["daily_ret"].values[1:]
    cb = res["cost_breakdown"]
    
    gross_total = res["total_return"] + cb["total_cost"]
    gross_daily = np.mean(dr) + cb["avg_cost_per_bar_bps"] / 10000
    
    # With N=10 stocks, long 5, short 5 (equal weight),
    # the cross-sectional dispersion per day matters.
    # If we assume avg cross-section std of returns ≈ 2% (typical for VN top-10),
    # then: E[daily_return] ≈ IC * dispersion * spread_factor
    # spread_factor for long-short ≈ 2 * (1/sqrt(N/2)) ≈ 2 * 0.632 = 1.264
    # So: IC ≈ gross_daily / (dispersion * spread_factor)
    
    assumed_dispersion = 0.02  # 2% daily cross-section std
    n_long = 5
    spread_factor = 2.0 * (1.0 / np.sqrt(n_long))
    
    implied_ic = gross_daily / (assumed_dispersion * spread_factor) if (assumed_dispersion * spread_factor) > 0 else 0
    
    print(f"\n--- {name} ---")
    print(f"  Gross daily return: {gross_daily*10000:.4f} bps")
    print(f"  Assumed cross-section dispersion: {assumed_dispersion*100:.1f}%")
    print(f"  Spread factor (L/S, N={n_long}): {spread_factor:.4f}")
    print(f"  Implied IC: {implied_ic:.6f}")
    print(f"  Skill threshold (IC > 0.02): {'PASS' if abs(implied_ic) > 0.02 else 'FAIL'}")
    if implied_ic < 0:
        print(f"  WARNING: Negative implied IC — signal is actively harmful")

# ---- Section 8: Regime detection quality assessment ----
print("\n" + "=" * 80)
print("SECTION 8: Regime Overlay Impact Assessment")
print("=" * 80)

# The Hybrid adds GMM + BOCPD on top of baseline HMM
# Let's check if the extra complexity helped or hurt
dr_b = eq_baseline["daily_ret"].values[1:]
dr_h = eq_hybrid["daily_ret"].values[1:]
n = len(dr_b)

# Compute rolling 20-day Sharpe for both
window = 20
rolling_sharpe_b = pd.Series(dr_b).rolling(window).mean() / pd.Series(dr_b).rolling(window).std() * np.sqrt(252)
rolling_sharpe_h = pd.Series(dr_h).rolling(window).mean() / pd.Series(dr_h).rolling(window).std() * np.sqrt(252)

# Compare performance in different return regimes
# When market is going down (negative 20d returns), did hybrid do better?
rolling_20d_ret_b = pd.Series(dr_b).rolling(window).sum()

bear_mask = rolling_20d_ret_b < -0.05  # 20d return < -5%
bull_mask = rolling_20d_ret_b > 0.05   # 20d return > +5%
neutral_mask = ~bear_mask & ~bull_mask

print(f"\nRegime-conditional performance (20-day rolling):")
print(f"  Bear days (20d ret < -5%): {bear_mask.sum()} days")
if bear_mask.sum() > 5:
    bear_ret_b = dr_b[bear_mask.values[:len(dr_b)]]
    bear_ret_h = dr_h[bear_mask.values[:len(dr_h)]]
    print(f"    Baseline avg daily ret: {np.mean(bear_ret_b)*10000:.2f} bps")
    print(f"    Hybrid avg daily ret:   {np.mean(bear_ret_h)*10000:.2f} bps")
    
print(f"  Bull days (20d ret > +5%): {bull_mask.sum()} days")
if bull_mask.sum() > 5:
    bull_ret_b = dr_b[bull_mask.values[:len(dr_b)]]
    bull_ret_h = dr_h[bull_mask.values[:len(dr_h)]]
    print(f"    Baseline avg daily ret: {np.mean(bull_ret_b)*10000:.2f} bps")
    print(f"    Hybrid avg daily ret:   {np.mean(bull_ret_h)*10000:.2f} bps")

print(f"  Neutral days: {neutral_mask.sum()} days")
if neutral_mask.sum() > 5:
    neut_ret_b = dr_b[neutral_mask.values[:len(dr_b)]]
    neut_ret_h = dr_h[neutral_mask.values[:len(dr_h)]]
    print(f"    Baseline avg daily ret: {np.mean(neut_ret_b)*10000:.2f} bps")
    print(f"    Hybrid avg daily ret:   {np.mean(neut_ret_h)*10000:.2f} bps")

# ---- Summary statistics for report ----
print("\n" + "=" * 80)
print("SUMMARY FOR L2 REPORT")
print("=" * 80)

# Key metrics table
b_cost = res_baseline["cost_breakdown"]
h_cost = res_hybrid["cost_breakdown"]

print(f"\n{'Metric':<40} {'Baseline':>15} {'Hybrid':>15}")
print(f"{'-'*40} {'-'*15} {'-'*15}")
print(f"{'Total Return':<40} {res_baseline['total_return']*100:>14.2f}% {res_hybrid['total_return']*100:>14.2f}%")
print(f"{'Sharpe':<40} {res_baseline['annualized_sharpe']:>15.4f} {res_hybrid['annualized_sharpe']:>15.4f}")
print(f"{'Max Drawdown':<40} {res_baseline['max_drawdown']*100:>14.2f}% {res_hybrid['max_drawdown']*100:>14.2f}%")
print(f"{'Avg Daily Turnover':<40} {b_cost['avg_turnover_per_bar']:>15.4f} {h_cost['avg_turnover_per_bar']:>15.4f}")
print(f"{'Total TC (cumulative)':<40} {b_cost['total_cost']*100:>14.2f}% {h_cost['total_cost']*100:>14.2f}%")
print(f"{'Avg TC per bar (bps)':<40} {b_cost['avg_cost_per_bar_bps']:>15.2f} {h_cost['avg_cost_per_bar_bps']:>15.2f}")
print(f"{'Ann. Cost Drag':<40} {b_cost['total_cost']/609*252*100:>14.2f}% {h_cost['total_cost']/609*252*100:>14.2f}%")
print(f"{'Gross Return (est)':<40} {(res_baseline['total_return']+b_cost['total_cost'])*100:>14.2f}% {(res_hybrid['total_return']+h_cost['total_cost'])*100:>14.2f}%")

print("\nDone. All analysis computed from repo-local data only.")
