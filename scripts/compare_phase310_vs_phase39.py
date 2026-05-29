"""Phase 3.10: compare Phase 3.9 (zero cold-start, dataset-median ADV)
vs Phase 3.10 (prev_w carry, expanding-median ADV)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("1B",   ".ly_state/session/phase3_9_full_1B.json",   ".ly_state/session/phase3_10_full_1B.json"),
    ("10B",  ".ly_state/session/phase3_9_full_10B.json",  ".ly_state/session/phase3_10_full_10B.json"),
    ("100B", ".ly_state/session/phase3_9_full_100B.json", ".ly_state/session/phase3_10_full_100B.json"),
]

print(f"{'cap':>5}  {'metric':>20}  {'Phase 3.9':>12}  {'Phase 3.10':>12}  {'delta':>10}")
print("-" * 70)
for label, p9_path, p10_path in cases:
    p9 = ROOT / p9_path
    p10 = ROOT / p10_path
    if not (p9.exists() and p10.exists()):
        print(f"{label:>5}  (missing)")
        continue
    with open(p9) as f:
        d9 = json.load(f)["baseline"]
    with open(p10) as f:
        d10 = json.load(f)["baseline"]

    metrics = [
        ("fold_DSR",         d9["fold_dsr"]["dsr"],            d10["fold_dsr"]["dsr"]),
        ("fold_SR_ann",      d9["fold_dsr"]["sr_mean_annualized"], d10["fold_dsr"]["sr_mean_annualized"]),
        ("pool_DSR",         d9["dsr"],                         d10["dsr"]),
        ("pool_SR_ann",      d9["dsr_sr_ann"],                  d10["dsr_sr_ann"]),
        ("avg_cost_bps",     d9["cost_breakdown"]["avg_cost_per_bar_bps"], d10["cost_breakdown"]["avg_cost_per_bar_bps"]),
        ("total_turnover",   d9["cost_breakdown"]["total_turnover"], d10["cost_breakdown"]["total_turnover"]),
        ("total_slippage",   d9["cost_breakdown"]["total_slippage_cost"], d10["cost_breakdown"]["total_slippage_cost"]),
        ("total_commission", d9["cost_breakdown"]["total_commission_cost"], d10["cost_breakdown"]["total_commission_cost"]),
    ]
    for name, v9, v10 in metrics:
        delta = v10 - v9
        print(f"{label:>5}  {name:>20}  {v9:>12.4g}  {v10:>12.4g}  {delta:>+10.4g}")
    print()
