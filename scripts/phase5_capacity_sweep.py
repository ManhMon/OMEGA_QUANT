"""Phase 5 capacity sweep + falsification report."""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

def load(name):
    return json.load(open(ROOT / ".ly_state/session" / name))["baseline"]

cases = [
    ("1B",   "phase5_full_1B_noLSTM.json",   1e9),
    ("5B",   "phase5_full_5B.json",          5e9),
    ("10B",  "phase5_full_10B_noLSTM.json",  1e10),
    ("30B",  "phase5_full_30B.json",         3e10),
    ("50B",  "phase5_full_50B.json",         5e10),
    ("100B", "phase5_full_100B_noLSTM.json", 1e11),
]

print("=" * 90)
print("CAPACITY SWEEP (Phase 5 clean baseline, full WF 2020-2024)")
print("=" * 90)
print(f"{'cap':>5} {'sr_ann':>8} {'fold_DSR':>9} {'med_IC':>8} {'cost_bps':>9} {'slip%':>7} {'turnover':>9} {'skew':>6} {'kurt':>6}")
print("-" * 90)
for label, fname, cap in cases:
    d = load(fname)
    fd = d["fold_dsr"]
    cb = d["cost_breakdown"]
    slip_pct = cb["total_slippage_cost"] / cb["total_cost"] * 100.0
    print(
        f"{label:>5} "
        f"{fd['sr_mean_annualized']:>8.3f} "
        f"{fd['dsr']:>9.4f} "
        f"{d['median_test_ic']:>8.4f} "
        f"{cb['avg_cost_per_bar_bps']:>9.2f} "
        f"{slip_pct:>6.1f}% "
        f"{cb['avg_turnover_per_bar']:>9.4f} "
        f"{fd['skew']:>+6.2f} "
        f"{fd['kurt']:>6.2f}"
    )
print()

# Falsification
print("=" * 90)
print("FALSIFICATION (y-shuffle, real alpha must collapse to ~0)")
print("=" * 90)
real = load("phase5_full_1B_noLSTM.json")
shuffle = load("phase5_full_1B_shuffle.json")
print(f"{'metric':>20} {'real':>12} {'y-shuffle':>12} {'verdict':>15}")
print("-" * 65)
for k, real_v, shuf_v in [
    ("median_test_ic", real["median_test_ic"], shuffle["median_test_ic"]),
    ("fold_SR_ann", real["fold_dsr"]["sr_mean_annualized"], shuffle["fold_dsr"]["sr_mean_annualized"]),
    ("fold_DSR", real["fold_dsr"]["dsr"], shuffle["fold_dsr"]["dsr"]),
    ("pool_SR_ann", real["dsr_sr_ann"], shuffle["dsr_sr_ann"]),
]:
    drop = abs(shuf_v) / max(abs(real_v), 1e-9)
    verdict = "PASS" if drop < 0.30 else ("WARN" if drop < 0.50 else "FAIL")
    print(f"{k:>20} {real_v:>+12.4f} {shuf_v:>+12.4f} {drop*100:>10.1f}% {verdict}")
print()

# Year-by-year breakdown for 1B
print("=" * 90)
print("FOLD STABILITY (1B, top-10 best vs top-10 worst folds)")
print("=" * 90)
folds = sorted(real["folds"], key=lambda f: f["fold_sr"], reverse=True)
print("Top 10 folds:")
for f in folds[:10]:
    print(f"  fold {f['fold']:>2}: SR {f['fold_sr']:>+7.3f}  IC {f['test_ic']:>+7.4f}  alpha {f['alpha']:>6}")
print("Bottom 10 folds:")
for f in folds[-10:]:
    print(f"  fold {f['fold']:>2}: SR {f['fold_sr']:>+7.3f}  IC {f['test_ic']:>+7.4f}  alpha {f['alpha']:>6}")
all_sr = np.array([f["fold_sr"] for f in real["folds"]])
print(f"\nFold SR distribution: mean={all_sr.mean():+.3f} med={np.median(all_sr):+.3f} std={all_sr.std():.3f} pos%={100*(all_sr > 0).sum() / len(all_sr):.0f}%")
