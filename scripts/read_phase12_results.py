"""Read Phase 12 Optuna results."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
d = json.load(open(ROOT / ".ly_state/session/phase12_full_50trials.json"))
print(f"Total trials: {d['n_trials']}")
print(f"Best fold_DSR (raw, n_trials=4): {d['best_fold_dsr_raw']:.4f}")
print(f"Best SR_ann: {d['best_sr_ann']:.3f}")
print(f"Best median IC: {d['best_median_ic']:.4f}")
print(f"Best params: {d['best_params']}")
print(f"Corrected n_trials: {d['best_fold_dsr_n_trials_corrected']}")
print(f"Note: {d['selection_bias_note']}")
print()
print("Top 5 trials by fold_DSR:")
trials = sorted(d["all_trials"], key=lambda t: t["fold_dsr"], reverse=True)
for t in trials[:5]:
    p = t["params"]
    print(f"  #{t['number']:>2}: DSR={t['fold_dsr']:.4f} SR={t['sr_ann']:.3f} IC={t['median_ic']:.4f} "
          f"h={p['label_horizon']} ema={p['signal_ema']} vol={p['vol_target']} "
          f"cap={p['max_abs_weight']} dd={p['dd_threshold']} emb={p['embargo_pct']}")
print()
print("Bottom 5 trials:")
for t in trials[-5:]:
    p = t["params"]
    print(f"  #{t['number']:>2}: DSR={t['fold_dsr']:.4f} SR={t['sr_ann']:.3f} h={p['label_horizon']} ema={p['signal_ema']}")
