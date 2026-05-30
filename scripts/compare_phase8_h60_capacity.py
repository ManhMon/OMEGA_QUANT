"""Phase 8 capacity sweep: h=60 vs h=20 baseline."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("1B",   "phase5_full_1B_noLSTM.json",   "phase8_h60_1B.json"),
    ("10B",  "phase5_full_10B_noLSTM.json",  "phase8_h60_10B.json"),
    ("100B", "phase5_full_100B_noLSTM.json", "phase8_h60_100B.json"),
]

print(f"{'cap':>5}  {'h=20 SR_ann':>12}  {'h=60 SR_ann':>12}  {'delta':>10}  {'h=20 cost':>10}  {'h=60 cost':>10}  {'h=20 IC':>9}  {'h=60 IC':>9}")
print("-" * 95)
for label, p20, p60 in cases:
    d20 = json.load(open(ROOT / ".ly_state/session" / p20))["baseline"]
    d60 = json.load(open(ROOT / ".ly_state/session" / p60))["baseline"]
    sr20 = d20["fold_dsr"]["sr_mean_annualized"]
    sr60 = d60["fold_dsr"]["sr_mean_annualized"]
    print(
        f"{label:>5}  "
        f"{sr20:>12.3f}  "
        f"{sr60:>12.3f}  "
        f"{(sr60 - sr20):>+10.3f}  "
        f"{d20['cost_breakdown']['avg_cost_per_bar_bps']:>10.2f}  "
        f"{d60['cost_breakdown']['avg_cost_per_bar_bps']:>10.2f}  "
        f"{d20['median_test_ic']:>9.4f}  "
        f"{d60['median_test_ic']:>9.4f}"
    )
