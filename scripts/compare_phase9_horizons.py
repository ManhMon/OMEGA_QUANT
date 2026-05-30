"""Phase 9: horizon fine-tune sweep h=20/40/60/80/120 @ 1B."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("h=20",  "phase5_full_1B_noLSTM.json"),
    ("h=40",  "phase9_h40_1B.json"),
    ("h=60",  "phase8_h60_1B.json"),
    ("h=80",  "phase9_h80_1B.json"),
    ("h=120", "phase9_h120_1B.json"),
]

print(f"{'horizon':>8} {'sr_ann':>8} {'fold_DSR':>9} {'med_IC':>8} {'cost_bps':>9} {'turnover':>9} {'pos%':>5} {'n_samples':>10}")
print("-" * 80)
for label, fname in cases:
    p = ROOT / ".ly_state/session" / fname
    if not p.exists():
        print(f"{label:>8} (missing {fname})")
        continue
    d = json.load(open(p))["baseline"]
    fd = d["fold_dsr"]
    cb = d["cost_breakdown"]
    sr = [f["fold_sr"] for f in d["folds"]]
    pos_pct = 100.0 * sum(1 for s in sr if s > 0) / len(sr)
    print(
        f"{label:>8} "
        f"{fd['sr_mean_annualized']:>8.3f} "
        f"{fd['dsr']:>9.4f} "
        f"{d['median_test_ic']:>8.4f} "
        f"{cb['avg_cost_per_bar_bps']:>9.2f} "
        f"{cb['avg_turnover_per_bar']:>9.4f} "
        f"{pos_pct:>4.0f}% "
        f"{d['n_samples']:>10}"
    )
