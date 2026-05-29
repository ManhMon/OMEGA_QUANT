"""Phase 3.8: Quick comparison of slippage cost vs portfolio capital."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cases = [
    ("1B", ".ly_state/session/phase3_8_smoke_1B.json"),
    ("10B", ".ly_state/session/phase3_8_smoke_10B.json"),
    ("100B", ".ly_state/session/phase3_8_smoke_100B.json"),
]

print(f"{'capital':>8} {'sr_ann':>8} {'cost_bps':>10} {'commission':>12} {'spread':>10} {'slip':>10} {'slip%':>8}")
print("-" * 70)
for label, rel in cases:
    p = ROOT / rel
    if not p.exists():
        print(f"{label:>8} (missing)")
        continue
    with open(p) as f:
        d = json.load(f)["baseline"]
    b = d["cost_breakdown"]
    total = b["total_cost"]
    slip_pct = (b["total_slippage_cost"] / total * 100.0) if total > 0 else 0.0
    print(
        f"{label:>8} "
        f"{d['dsr_sr_ann']:>8.3f} "
        f"{b['avg_cost_per_bar_bps']:>10.2f} "
        f"{b['total_commission_cost']:>12.4f} "
        f"{b['total_spread_cost']:>10.4f} "
        f"{b['total_slippage_cost']:>10.4f} "
        f"{slip_pct:>7.1f}%"
    )
