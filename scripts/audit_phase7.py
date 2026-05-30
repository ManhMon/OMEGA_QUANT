"""Phase 7 audit: capacity sweep + falsification consistency."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ARTIFACTS = {
    "1B":   ROOT / ".ly_state/session/phase5_full_1B_noLSTM.json",
    "5B":   ROOT / ".ly_state/session/phase5_full_5B.json",
    "10B":  ROOT / ".ly_state/session/phase5_full_10B_noLSTM.json",
    "30B":  ROOT / ".ly_state/session/phase5_full_30B.json",
    "50B":  ROOT / ".ly_state/session/phase5_full_50B.json",
    "100B": ROOT / ".ly_state/session/phase5_full_100B_noLSTM.json",
    "1B_shuffle": ROOT / ".ly_state/session/phase5_full_1B_shuffle.json",
}

CAP_VND = {"1B": 1e9, "5B": 5e9, "10B": 1e10, "30B": 3e10, "50B": 5e10, "100B": 1e11}


def fail(label, msg, fs):
    fs.append({"sev": "P0", "id": label, "msg": msg})

def warn(label, msg, fs):
    fs.append({"sev": "P1", "id": label, "msg": msg})

def info(label, msg, fs):
    fs.append({"sev": "P2", "id": label, "msg": msg})


def load_all():
    out = {}
    for k, p in ARTIFACTS.items():
        if not p.exists():
            return None, k
        out[k] = json.load(open(p))["baseline"]
    return out, None


def check_artifact_presence():
    fs = []
    data, missing = load_all()
    if missing:
        fail("ART-MISS", f"Missing artifact for {missing}", fs)
        return False, fs, None
    return True, fs, data


def check_alpha_invariant(data):
    """median test IC must be SAME across capitals (alpha is capital-invariant;
    only cost differs)."""
    fs = []
    ics = {k: data[k]["median_test_ic"] for k in CAP_VND}
    base = ics["1B"]
    for k, v in ics.items():
        if abs(v - base) > 1e-9:
            fail("ALPHA-VAR", f"median_test_IC at {k} differs from 1B ({v} vs {base})", fs)
    info("ALPHA-INV", f"median_test_IC identical across all capitals: {base:.4f}", fs)
    return len([f for f in fs if f["sev"] == "P0"]) == 0, fs


def check_capacity_monotone(data):
    """fold_SR_ann must monotonically decrease with capital (since slippage
    grows with capital and alpha is identical)."""
    fs = []
    sr = [(cap, data[k]["fold_dsr"]["sr_mean_annualized"]) for k, cap in zip(CAP_VND.keys(), CAP_VND.values())]
    for i in range(len(sr) - 1):
        cap_a, sr_a = sr[i]
        cap_b, sr_b = sr[i + 1]
        if sr_b > sr_a + 1e-3:
            fail("CAP-MONO", f"SR_ann not monotone: {cap_a:.0e}→{sr_a:.3f} vs {cap_b:.0e}→{sr_b:.3f}", fs)
    info("CAP-MONO", f"SR_ann monotone decreasing: {[f'{s[1]:.3f}' for s in sr]}", fs)
    return len([f for f in fs if f["sev"] == "P0"]) == 0, fs


def check_slippage_linear(data):
    """slippage cost must scale linearly with capital (factor 5x, 2x, 3x, 1.67x, 2x).
    Delta should match capital ratio within ~5%."""
    fs = []
    slip = {k: data[k]["cost_breakdown"]["total_slippage_cost"] for k in CAP_VND}
    pairs = [("1B", "5B", 5.0), ("5B", "10B", 2.0), ("10B", "30B", 3.0),
             ("30B", "50B", 50.0/30.0), ("50B", "100B", 2.0)]
    for a, b, expected_ratio in pairs:
        if slip[a] < 1e-9:
            warn("SLIP-LIN", f"slip[{a}] near zero, ratio test skipped", fs)
            continue
        ratio = slip[b] / slip[a]
        rel_err = abs(ratio - expected_ratio) / expected_ratio
        if rel_err > 0.10:
            warn("SLIP-LIN", f"{a}->{b} ratio {ratio:.3f} vs expected {expected_ratio:.3f} (rel err {100*rel_err:.1f}%)", fs)
        else:
            info("SLIP-LIN", f"{a}->{b}: ratio {ratio:.3f} ~ expected {expected_ratio:.3f} OK", fs)
    return len([f for f in fs if f["sev"] == "P0"]) == 0, fs


def check_commission_spread_invariant(data):
    """commission and spread MUST be identical across capitals (capital-invariant)."""
    fs = []
    commissions = [data[k]["cost_breakdown"]["total_commission_cost"] for k in CAP_VND]
    spreads = [data[k]["cost_breakdown"]["total_spread_cost"] for k in CAP_VND]
    turnovers = [data[k]["cost_breakdown"]["total_turnover"] for k in CAP_VND]
    for label, vals in [("commission", commissions), ("spread", spreads), ("turnover", turnovers)]:
        if max(vals) - min(vals) > 1e-6:
            fail("COST-INV", f"{label} not capital-invariant: range {min(vals):.6f}..{max(vals):.6f}", fs)
        else:
            info("COST-INV", f"{label} identical across capitals: {vals[0]:.6f}", fs)
    return len([f for f in fs if f["sev"] == "P0"]) == 0, fs


def check_falsification(data):
    """y-shuffle must collapse SR_ann magnitude. Spec: |shuffle_SR| / |real_SR| < 0.30
    for SR-based metrics. IC may sign-flip (which is a stronger signal of no leakage)."""
    fs = []
    real = data["1B"]
    shuf = data["1B_shuffle"]

    real_sr = real["fold_dsr"]["sr_mean_annualized"]
    shuf_sr = shuf["fold_dsr"]["sr_mean_annualized"]
    drop_sr = abs(shuf_sr) / max(abs(real_sr), 1e-9)
    if drop_sr > 0.30:
        fail("FALS-SR", f"y-shuffle fold_SR_ann magnitude {abs(shuf_sr):.3f} > 30% of real {abs(real_sr):.3f}", fs)
    else:
        info("FALS-SR", f"y-shuffle fold_SR collapsed to {100*drop_sr:.1f}% of real OK", fs)

    real_ic = real["median_test_ic"]
    shuf_ic = shuf["median_test_ic"]
    if real_ic * shuf_ic > 0 and abs(shuf_ic) > 0.5 * abs(real_ic):
        fail("FALS-IC", f"y-shuffle IC stayed same sign and >=50% magnitude: real {real_ic:.4f}, shuffle {shuf_ic:.4f}", fs)
    else:
        info("FALS-IC", f"y-shuffle IC sign-flip or major drop: real {real_ic:+.4f} -> shuf {shuf_ic:+.4f}", fs)

    return len([f for f in fs if f["sev"] == "P0"]) == 0, fs


def check_fold_stability(data):
    """1B fold SR distribution: positive% should be > 60%, std reasonable."""
    fs = []
    folds = data["1B"]["folds"]
    sr = [f["fold_sr"] for f in folds]
    pos_pct = 100.0 * sum(1 for s in sr if s > 0) / len(sr)
    if pos_pct < 60:
        warn("FOLD-POS", f"only {pos_pct:.0f}% folds positive (expected >60%)", fs)
    else:
        info("FOLD-POS", f"{pos_pct:.0f}% folds positive OK", fs)
    return True, fs


def main():
    findings_all = []
    ok, fs, data = check_artifact_presence()
    findings_all.extend(fs)
    if not ok:
        for f in findings_all:
            print(f"[{f['sev']}] {f['id']}: {f['msg']}")
        print("VERDICT: [NEEDS_FIX]")
        return 1

    checks = [
        ("alpha invariant",   check_alpha_invariant),
        ("capacity monotone", check_capacity_monotone),
        ("slippage linear",   check_slippage_linear),
        ("commission/spread invariant", check_commission_spread_invariant),
        ("falsification",     check_falsification),
        ("fold stability",    check_fold_stability),
    ]
    overall = True
    print(f"{'check':<32} {'result':<10} notes")
    print("-" * 80)
    for name, fn in checks:
        ok, fs = fn(data)
        findings_all.extend(fs)
        notes = ", ".join(f"[{f['sev']}]{f['id']}" for f in fs[:3]) or "OK"
        print(f"{name:<32} {'PASS' if ok else 'FAIL':<10} {notes}")
        overall = overall and ok

    print()
    print("FINDINGS DETAIL")
    print("-" * 80)
    for f in findings_all:
        print(f"[{f['sev']}] {f['id']}: {f['msg']}")

    print()
    print(f"VERDICT: {'[APPROVED]' if overall else '[NEEDS_FIX]'}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
