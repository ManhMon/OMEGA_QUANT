"""Compare Phase 3.11 (dirty data) vs Phase 5 (clean data) capacity sweep."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("1B",   ".ly_state/session/phase3_11_full_1B.json",   ".ly_state/session/phase5_full_1B_noLSTM.json"),
    ("10B",  ".ly_state/session/phase3_11_full_10B.json",  ".ly_state/session/phase5_full_10B_noLSTM.json"),
    ("100B", ".ly_state/session/phase3_11_full_100B.json", ".ly_state/session/phase5_full_100B_noLSTM.json"),
]

print(f"{'cap':>5}  {'metric':>20}  {'Phase 3.11 (dirty)':>20}  {'Phase 5 (clean)':>18}  {'delta':>10}")
print("-" * 85)
for label, p311, p5 in cases:
    with open(ROOT / p311) as f:
        d_dirty = json.load(f)["baseline"]
    with open(ROOT / p5) as f:
        d_clean = json.load(f)["baseline"]

    rows = [
        ("n_samples",       d_dirty["n_samples"],                       d_clean["n_samples"]),
        ("median_test_IC",  d_dirty["median_test_ic"],                  d_clean["median_test_ic"]),
        ("fold_SR_ann",     d_dirty["fold_dsr"]["sr_mean_annualized"],  d_clean["fold_dsr"]["sr_mean_annualized"]),
        ("fold_DSR",        d_dirty["fold_dsr"]["dsr"],                 d_clean["fold_dsr"]["dsr"]),
        ("pool_SR_ann",     d_dirty["dsr_sr_ann"],                      d_clean["dsr_sr_ann"]),
        ("avg_cost_bps",    d_dirty["cost_breakdown"]["avg_cost_per_bar_bps"], d_clean["cost_breakdown"]["avg_cost_per_bar_bps"]),
        ("turnover/bar",    d_dirty["cost_breakdown"]["avg_turnover_per_bar"], d_clean["cost_breakdown"]["avg_turnover_per_bar"]),
        ("slip_share_pct",  100.0 * d_dirty["cost_breakdown"]["total_slippage_cost"] / d_dirty["cost_breakdown"]["total_cost"],
                            100.0 * d_clean["cost_breakdown"]["total_slippage_cost"] / d_clean["cost_breakdown"]["total_cost"]),
    ]
    for name, vd, vc in rows:
        delta = vc - vd
        sign = "+" if delta >= 0 else ""
        print(f"{label:>5}  {name:>20}  {vd:>20.4g}  {vc:>18.4g}  {sign}{delta:>9.4g}")
    print()
