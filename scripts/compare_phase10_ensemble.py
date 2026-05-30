"""Phase 10 ensemble comparison."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("h=20 only",  "phase5_full_1B_noLSTM.json"),
    ("h=60 only",  "phase8_h60_1B.json"),
    ("h=80 only",  "phase9_h80_1B.json"),
    ("ens 20+60",  "phase10_ens_20_60_1B.json"),
    ("ens 60+80",  "phase10_ens_60_80_1B.json"),
]

print(f"{'config':>15} {'sr_ann':>8} {'fold_DSR':>9} {'med_IC':>8} {'cost_bps':>9} {'turnover':>9}")
print("-" * 70)
for label, fname in cases:
    p = ROOT / ".ly_state/session" / fname
    if not p.exists():
        print(f"{label:>15} (missing)")
        continue
    d = json.load(open(p))["baseline"]
    fd = d["fold_dsr"]
    cb = d["cost_breakdown"]
    print(
        f"{label:>15} "
        f"{fd['sr_mean_annualized']:>8.3f} "
        f"{fd['dsr']:>9.4f} "
        f"{d['median_test_ic']:>8.4f} "
        f"{cb['avg_cost_per_bar_bps']:>9.2f} "
        f"{cb['avg_turnover_per_bar']:>9.4f}"
    )
