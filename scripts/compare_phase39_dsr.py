"""Phase 3.9: compare pooled DSR vs fold-level DSR across capitals."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("1B",   ".ly_state/session/phase3_9_full_1B.json"),
    ("10B",  ".ly_state/session/phase3_9_full_10B.json"),
    ("100B", ".ly_state/session/phase3_9_full_100B.json"),
]

print(
    f"{'cap':>5} {'pool_DSR':>10} {'pool_SR_an':>11} "
    f"{'fold_DSR':>10} {'fold_SR_an':>11} {'fold_skew':>10} {'fold_kurt':>10}"
)
print("-" * 75)
for label, rel in cases:
    p = ROOT / rel
    if not p.exists():
        print(f"{label:>5} (missing)")
        continue
    with open(p) as f:
        d = json.load(f)["baseline"]
    fd = d.get("fold_dsr", {})
    print(
        f"{label:>5} "
        f"{d['dsr']:>10.3e} "
        f"{d['dsr_sr_ann']:>11.3f} "
        f"{fd.get('dsr', 0):>10.4f} "
        f"{fd.get('sr_mean_annualized', 0):>11.3f} "
        f"{fd.get('skew', 0):>10.3f} "
        f"{fd.get('kurt', 0):>10.2f}"
    )
print()
print("Pooled DSR uses 11142 daily bars (oversampled ~9x by overlapping CPCV).")
print("Fold-level DSR uses 45 fold Sharpes (one IID obs per CPCV fold).")
