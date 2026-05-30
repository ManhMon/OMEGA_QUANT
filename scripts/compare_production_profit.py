"""Phase 8 vs Phase 5 production comparison: backtest metrics + simulated annual profit.

Computes annualized profit (gross + net) across 1B/10B/100B for each strategy.
Annual gross profit = capital * SR_ann * sigma_ann
where sigma_ann is implied from SR and pool sharpe (we use 15% target vol from
tail_controls vol_target setting in execution_sim).

Note: backtest sigma is ALREADY post-tail-control (vol-targeted to 15%).
So annual_gross_return = SR_ann * 0.15 (very close approximation).
Annual net = annual_gross - annual_cost.
Annual cost = avg_cost_per_bar_bps * 1e-4 * 252 (252 bars/year).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Phase 5 baseline (h=20)
P5 = {
    "1B":   "phase5_full_1B_noLSTM.json",
    "5B":   "phase5_full_5B.json",
    "10B":  "phase5_full_10B_noLSTM.json",
    "30B":  "phase5_full_30B.json",
    "50B":  "phase5_full_50B.json",
    "100B": "phase5_full_100B_noLSTM.json",
}
# Phase 8 production candidate (h=60)
P8 = {
    "1B":   "phase8_h60_1B.json",
    "10B":  "phase8_h60_10B.json",
    "100B": "phase8_h60_100B.json",
}
CAP_VND = {"1B": 1e9, "5B": 5e9, "10B": 1e10, "30B": 3e10, "50B": 5e10, "100B": 1e11}

VOL_TARGET = 0.15  # 15% annualized vol target from execution_sim
BARS_PER_YEAR = 252


def load(fname):
    return json.load(open(ROOT / ".ly_state/session" / fname))["baseline"]


def annual_metrics(d, capital):
    sr_ann = d["fold_dsr"]["sr_mean_annualized"]
    cost_bps = d["cost_breakdown"]["avg_cost_per_bar_bps"]
    # Estimated annual gross return = SR * vol target (since strategy is
    # vol-targeted by tail_controls).
    gross_pct = sr_ann * VOL_TARGET * 100.0
    cost_pct = cost_bps * 1e-4 * BARS_PER_YEAR * 100.0
    net_pct = gross_pct - cost_pct
    gross_vnd = capital * gross_pct / 100.0
    net_vnd = capital * net_pct / 100.0
    return {
        "sr_ann": sr_ann,
        "gross_pct": gross_pct,
        "cost_pct": cost_pct,
        "net_pct": net_pct,
        "gross_vnd": gross_vnd,
        "net_vnd": net_vnd,
        "fold_dsr": d["fold_dsr"]["dsr"],
        "median_ic": d["median_test_ic"],
    }


def fmt_vnd(v):
    if abs(v) >= 1e9:
        return f"{v/1e9:+,.2f}B"
    if abs(v) >= 1e6:
        return f"{v/1e6:+,.0f}M"
    return f"{v:+,.0f}"


print("=" * 100)
print("PHASE 5 (h=20) — BASELINE PRODUCTION")
print("=" * 100)
print(f"{'cap':>5} {'SR_ann':>8} {'fold_DSR':>9} {'med_IC':>8} {'gross/yr':>10} {'cost/yr':>9} {'net/yr':>9} {'net VND/yr':>14}")
print("-" * 100)
for k, fname in P5.items():
    d = load(fname)
    m = annual_metrics(d, CAP_VND[k])
    print(f"{k:>5} {m['sr_ann']:>+8.3f} {m['fold_dsr']:>9.4f} {m['median_ic']:>+8.4f} "
          f"{m['gross_pct']:>+9.2f}% {m['cost_pct']:>8.2f}% {m['net_pct']:>+8.2f}% {fmt_vnd(m['net_vnd']):>14}")

print()
print("=" * 100)
print("PHASE 8 (h=60) — PRODUCTION CANDIDATE")
print("=" * 100)
print(f"{'cap':>5} {'SR_ann':>8} {'fold_DSR':>9} {'med_IC':>8} {'gross/yr':>10} {'cost/yr':>9} {'net/yr':>9} {'net VND/yr':>14}")
print("-" * 100)
for k, fname in P8.items():
    d = load(fname)
    m = annual_metrics(d, CAP_VND[k])
    print(f"{k:>5} {m['sr_ann']:>+8.3f} {m['fold_dsr']:>9.4f} {m['median_ic']:>+8.4f} "
          f"{m['gross_pct']:>+9.2f}% {m['cost_pct']:>8.2f}% {m['net_pct']:>+8.2f}% {fmt_vnd(m['net_vnd']):>14}")

print()
print("=" * 100)
print("DELTA: Phase 8 (h=60) vs Phase 5 (h=20)")
print("=" * 100)
print(f"{'cap':>5} {'SR delta':>10} {'net % delta':>12} {'extra VND/yr':>16}")
print("-" * 60)
for k in ["1B", "10B", "100B"]:
    d5 = load(P5[k])
    d8 = load(P8[k])
    m5 = annual_metrics(d5, CAP_VND[k])
    m8 = annual_metrics(d8, CAP_VND[k])
    sr_delta = m8["sr_ann"] - m5["sr_ann"]
    net_pct_delta = m8["net_pct"] - m5["net_pct"]
    extra_vnd = m8["net_vnd"] - m5["net_vnd"]
    print(f"{k:>5} {sr_delta:>+10.3f} {net_pct_delta:>+11.2f}% {fmt_vnd(extra_vnd):>16}")

print()
print("Notes:")
print("  - SR_ann is post-cost annualized Sharpe ratio (vol-targeted).")
print("  - gross_pct = SR_ann * 15% (vol target), approximate annual return BEFORE cost.")
print("  - cost_pct = avg_cost_per_bar_bps * 252 / 10000, deducted to give net.")
print("  - net VND/yr is realistic estimate at face capital, NOT compounded.")
