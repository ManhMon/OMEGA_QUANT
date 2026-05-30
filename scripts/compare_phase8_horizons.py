"""Phase 8 horizon comparison: h=5 vs h=20 vs h=60."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("h=5",  "phase8_h5_1B.json"),
    ("h=20", "phase5_full_1B_noLSTM.json"),
    ("h=60", "phase8_h60_1B.json"),
]

print(f"{'horizon':>8} {'sr_ann':>8} {'fold_DSR':>9} {'med_IC':>9} {'cost_bps':>9} {'turnover':>9} {'fold_pos%':>10}")
print("-" * 75)
for label, fname in cases:
    p = ROOT / ".ly_state/session" / fname
    if not p.exists():
        print(f"{label:>8} (missing)")
        continue
    with open(p) as f:
        d = json.load(f)["baseline"]
    fd = d["fold_dsr"]
    cb = d["cost_breakdown"]
    sr = [f["fold_sr"] for f in d["folds"]]
    pos_pct = 100.0 * sum(1 for s in sr if s > 0) / len(sr)
    print(
        f"{label:>8} "
        f"{fd['sr_mean_annualized']:>8.3f} "
        f"{fd['dsr']:>9.4f} "
        f"{d['median_test_ic']:>9.4f} "
        f"{cb['avg_cost_per_bar_bps']:>9.2f} "
        f"{cb['avg_turnover_per_bar']:>9.4f} "
        f"{pos_pct:>9.0f}%"
    )
