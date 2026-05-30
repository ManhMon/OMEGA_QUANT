"""Phase 4 LSTM smoke / full result summarizer."""
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
p = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".ly_state/session/phase4_smoke_1B.json"
with open(p) as f:
    d = json.load(f)["baseline"]
fd = d.get("fold_dsr", {})
b = d.get("cost_breakdown", {})
ic_lstms = [f.get("ic_lstm") for f in d["folds"] if f.get("ic_lstm") is not None]

print(f"file: {p.name}")
print(f"  n_samples={d['n_samples']} n_folds={d['n_folds']} n_daily={d['n_daily']}")
print(f"  pool SR_ann = {d['dsr_sr_ann']:.3f}   pool DSR = {d['dsr']:.3e}")
print(f"  fold SR_ann = {fd.get('sr_mean_annualized', 0):.3f}   fold DSR = {fd.get('dsr', 0):.4f}")
print(f"  median test IC (Ridge):     {d['median_test_ic']:.4f}")
if ic_lstms:
    print(f"  median test IC (LSTM):      {float(np.median(ic_lstms)):.4f}  ({len(ic_lstms)} folds)")
if b:
    slip_pct = (b['total_slippage_cost'] / b['total_cost'] * 100.0) if b['total_cost'] > 0 else 0.0
    print(f"  cost: {b['avg_cost_per_bar_bps']:.2f} bps/bar   turnover: {b['avg_turnover_per_bar']:.3f}/bar   capital: {b['capital_vnd']:.0e}")
    print(f"  commission={b['total_commission_cost']:.4f} spread={b['total_spread_cost']:.4f} slip={b['total_slippage_cost']:.4f} ({slip_pct:.1f}%)")
