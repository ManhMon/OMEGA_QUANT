"""Quick summary of one phase 3.8 result file."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

p = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".ly_state/session/phase3_8_full_10B.json"
with open(p) as f:
    d = json.load(f)["baseline"]
b = d.get("cost_breakdown", {})

print(f"file: {p.name}")
print(f"  n_samples={d['n_samples']} n_folds={d['n_folds']} n_daily={d['n_daily']}")
print(
    f"  med_test_IC={d['median_test_ic']:.4f} "
    f"med_train_IC={d['median_train_cv_ic']:.4f} "
    f"med_fold_SR={d['median_fold_sr']:.4f}"
)
print(
    f"  SR_ann={d['dsr_sr_ann']:.3f} DSR={d['dsr']:.3e} "
    f"skew={d['skew']:.2f} kurt={d['kurt']:.1f}"
)
if b:
    total = b["total_cost"]
    slip_pct = (b["total_slippage_cost"] / total * 100.0) if total > 0 else 0.0
    print(
        f"  cost={b['avg_cost_per_bar_bps']:.2f}bps/bar "
        f"turnover={b['avg_turnover_per_bar']:.3f}/bar "
        f"capital={b['capital_vnd']:.0e}"
    )
    print(
        f"  commission={b['total_commission_cost']:.4f} "
        f"spread={b['total_spread_cost']:.4f} "
        f"slip={b['total_slippage_cost']:.4f} "
        f"({slip_pct:.1f}% of total)"
    )
