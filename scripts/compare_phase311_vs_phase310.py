"""Phase 3.11 vs Phase 3.10: EMA reset per (ticker, contiguous block)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("1B",   ".ly_state/session/phase3_10_full_1B.json",   ".ly_state/session/phase3_11_full_1B.json"),
    ("10B",  ".ly_state/session/phase3_10_full_10B.json",  ".ly_state/session/phase3_11_full_10B.json"),
    ("100B", ".ly_state/session/phase3_10_full_100B.json", ".ly_state/session/phase3_11_full_100B.json"),
]

print(f"{'cap':>5}  {'metric':>20}  {'Phase 3.10':>12}  {'Phase 3.11':>12}  {'delta':>10}")
print("-" * 70)
for label, p10_path, p11_path in cases:
    p10 = ROOT / p10_path
    p11 = ROOT / p11_path
    with open(p10) as f:
        d10 = json.load(f)["baseline"]
    with open(p11) as f:
        d11 = json.load(f)["baseline"]

    metrics = [
        ("fold_DSR",         d10["fold_dsr"]["dsr"],            d11["fold_dsr"]["dsr"]),
        ("fold_SR_ann",      d10["fold_dsr"]["sr_mean_annualized"], d11["fold_dsr"]["sr_mean_annualized"]),
        ("pool_SR_ann",      d10["dsr_sr_ann"],                  d11["dsr_sr_ann"]),
        ("avg_cost_bps",     d10["cost_breakdown"]["avg_cost_per_bar_bps"], d11["cost_breakdown"]["avg_cost_per_bar_bps"]),
        ("total_turnover",   d10["cost_breakdown"]["total_turnover"], d11["cost_breakdown"]["total_turnover"]),
    ]
    for name, v10, v11 in metrics:
        delta = v11 - v10
        sign = "+" if delta >= 0 else ""
        print(f"{label:>5}  {name:>20}  {v10:>12.4g}  {v11:>12.4g}  {sign}{delta:>9.4g}")
    print()
