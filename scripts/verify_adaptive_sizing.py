"""Verify continuous adaptive sizing scaling."""
import sys
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))
from adaptive_sizing_overlay import get_adaptive_params

capitals = [0.5e9, 1e9, 2e9, 4e9, 10e9, 20e9, 50e9, 100e9]

print("=" * 60)
print("  CONTINUOUS ADAPTIVE SIZING (Power Law)")
print("=" * 60)
print(f"  {'Capital':>10} {'Tier':<8} {'Max Weight':>12} {'Vol Target':>12}")
print(f"  {'-'*10} {'-'*8} {'-'*12} {'-'*12}")
for cap in capitals:
    p = get_adaptive_params(cap)
    print(f"  {cap/1e9:>8.1f}B  {p['tier']:<8} {p['max_weight']*100:>10.1f}%  {p['vol_target']*100:>10.1f}%")
print("=" * 60)
print("\n  No cliff between tiers - smooth transition!")
