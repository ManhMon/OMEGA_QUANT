"""Phase 11: idealized vs realistic cost model comparison."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VOL_TARGET = 0.15
BARS = 252


def load(name):
    return json.load(open(ROOT / ".ly_state/session" / name))["baseline"]


def metrics(d, capital):
    sr = d["fold_dsr"]["sr_mean_annualized"]
    cost_bps = d["cost_breakdown"]["avg_cost_per_bar_bps"]
    gross = sr * VOL_TARGET * 100.0
    cost = cost_bps * 1e-4 * BARS * 100.0
    net = gross - cost
    return {"sr": sr, "gross": gross, "cost": cost, "net": net,
            "net_vnd": capital * net / 100.0,
            "fdsr": d["fold_dsr"]["dsr"]}


cases = [
    ("1B",   1e9,  "phase8_h60_1B.json",   "phase11_realistic_1B.json"),
    ("10B",  1e10, "phase8_h60_10B.json",  "phase11_realistic_10B.json"),
    ("100B", 1e11, "phase8_h60_100B.json", "phase11_realistic_100B.json"),
]

print("=" * 95)
print("PHASE 8 (h=60 idealized) vs PHASE 11 (h=60 + realistic cost model)")
print("Phase 11 knobs: slip-nonlinear-exp=0.6 (Almgren-Chriss-ish),")
print("                settlement-lag=T+2.5, halt-haircut=5bps/bar, foreign-haircut=2bps/bar")
print("=" * 95)
print()
print(f"{'cap':>5}  {'P8 SR':>7}  {'P8 net%':>9}  {'P8 VND/yr':>14}    {'P11 SR':>7}  {'P11 net%':>10}  {'P11 VND/yr':>14}")
print("-" * 95)
for cap, vnd, p8, p11 in cases:
    m8 = metrics(load(p8), vnd)
    m11 = metrics(load(p11), vnd)
    p8_str = f"{m8['net_vnd']/1e9:+,.2f}B" if abs(m8['net_vnd']) >= 1e9 else f"{m8['net_vnd']/1e6:+,.0f}M"
    p11_str = f"{m11['net_vnd']/1e9:+,.2f}B" if abs(m11['net_vnd']) >= 1e9 else f"{m11['net_vnd']/1e6:+,.0f}M"
    print(f"{cap:>5}  {m8['sr']:>+7.3f}  {m8['net']:>+8.2f}%  {p8_str:>14}    "
          f"{m11['sr']:>+7.3f}  {m11['net']:>+9.2f}%  {p11_str:>14}")

print()
print("Delta (P11 vs P8 = realistic vs idealized cost):")
for cap, vnd, p8, p11 in cases:
    m8 = metrics(load(p8), vnd)
    m11 = metrics(load(p11), vnd)
    sr_delta = m11['sr'] - m8['sr']
    net_delta = m11['net_vnd'] - m8['net_vnd']
    delta_str = f"{net_delta/1e9:+,.2f}B" if abs(net_delta) >= 1e9 else f"{net_delta/1e6:+,.0f}M"
    print(f"  {cap:>5}: SR {sr_delta:>+6.3f}, net VND/yr delta = {delta_str}")
