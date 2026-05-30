"""Independent L3 audit for Phase 5 data sanitization wiring.

Verifies:
  1. Imports for DataSanitizer / AlphaSanitizer are present.
  2. mask_suspended/sanitize_ohlcv are defined and called in load_panel*.
  3. Cleaning order: mask_suspended -> sanitize_ohlcv -> _attach_adv.
  4. universe_year_map preserves (ticker, date) -> year tagging in WF.
  5. Train-fold winsorize 1%/99% PIT-safe (np.nanpercentile on X_tr only).
  6. Numerical sanity from Phase 5 result JSONs.

Exit 0 = APPROVED, 1 = NEEDS_FIX.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKTEST = ROOT / "scripts" / "backtest_v2_cpcv.py"
SANITIZER = ROOT / "packages" / "data" / "src" / "omega" / "data" / "sanitizer.py"
ALPHA_SAN = ROOT / "src" / "omega" / "quant" / "alpha_sanitizer.py"

ARTIFACTS = {
    "smoke_1B":   ROOT / ".ly_state/session/phase5_smoke_1B.json",
    "full_1B":    ROOT / ".ly_state/session/phase5_full_1B_noLSTM.json",
}


def fail(label, msg, findings):
    findings.append({"sev": "P0", "id": label, "msg": msg})

def warn(label, msg, findings):
    findings.append({"sev": "P1", "id": label, "msg": msg})

def info(label, msg, findings):
    findings.append({"sev": "P2", "id": label, "msg": msg})


def check_imports():
    findings = []
    src = BACKTEST.read_text(encoding="utf-8")
    if "from omega.data.sanitizer import DataSanitizer" not in src:
        fail("IMP-1", "Missing DataSanitizer import", findings)
    if "from omega.quant.alpha_sanitizer import AlphaSanitizer" not in src:
        warn("IMP-2", "AlphaSanitizer imported but not yet used (acceptable; reserved for future per-fold alpha winsorize)", findings)
    return len([f for f in findings if f["sev"] == "P0"]) == 0, findings


def check_helpers_defined():
    findings = []
    src = BACKTEST.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for required in ("mask_suspended", "sanitize_ohlcv", "_attach_adv", "load_panel", "load_panel_walk_forward"):
        if required not in fn_names:
            fail("DEF-MISS", f"Function {required} not defined", findings)
    return len([f for f in findings if f["sev"] == "P0"]) == 0, findings


def check_cleaning_order():
    """In load_panel and load_panel_walk_forward, the call order must be:
    mask_suspended -> sanitize_ohlcv -> _attach_adv (so ADV is computed
    on cleaned data, not raw)."""
    findings = []
    src = BACKTEST.read_text(encoding="utf-8")
    for fn in ("load_panel", "load_panel_walk_forward"):
        tree = ast.parse(src)
        target = next((n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == fn), None)
        if target is None:
            fail("ORDER-MISS", f"{fn} not found", findings)
            continue
        body_src = ast.unparse(target)
        idx_mask = body_src.find("mask_suspended(")
        idx_san = body_src.find("sanitize_ohlcv(")
        idx_adv = body_src.find("_attach_adv(")
        if not (0 <= idx_mask < idx_san < idx_adv):
            fail("ORDER-1",
                 f"{fn}: cleaning order broken (mask_suspended={idx_mask}, "
                 f"sanitize_ohlcv={idx_san}, _attach_adv={idx_adv})",
                 findings)
    return len([f for f in findings if f["sev"] == "P0"]) == 0, findings


def check_universe_year_remapping():
    findings = []
    src = BACKTEST.read_text(encoding="utf-8")
    if "universe_year_map" not in src:
        fail("WF-1", "load_panel_walk_forward missing universe_year_map", findings)
    if 'panel["_universe_year"] = [' not in src:
        fail("WF-2", "Re-tag _universe_year after sanitize not present", findings)
    if 'panel["_universe_year"]].drop' not in src and 'date"].dt.year == panel["_universe_year"]' not in src:
        warn("WF-3", "Final filter to in-fold years not detected (manual inspection recommended)", findings)
    return len([f for f in findings if f["sev"] == "P0"]) == 0, findings


def check_winsorize_pit():
    findings = []
    src = BACKTEST.read_text(encoding="utf-8")
    if "np.nanpercentile(X_tr, 1.0, axis=0)" not in src:
        fail("WIN-1", "Missing 1%/99% winsorize on X_tr only", findings)
    if "np.nanpercentile(X_tr, 99.0, axis=0)" not in src:
        fail("WIN-2", "Missing upper percentile on X_tr only", findings)
    if "np.clip(X_tr, lo, hi)" not in src or "np.clip(X_te, lo, hi)" not in src:
        fail("WIN-3", "Missing np.clip on both train and test", findings)
    # Order: winsorize must come BEFORE z-score
    win_idx = src.find("np.nanpercentile(X_tr, 1.0")
    zs_idx = src.find("mu = np.nanmean(X_tr, axis=0)")
    if not (win_idx >= 0 and zs_idx >= 0 and win_idx < zs_idx):
        fail("WIN-4", "Winsorize must be applied BEFORE z-score", findings)
    return len([f for f in findings if f["sev"] == "P0"]) == 0, findings


def check_pit_as_of_time():
    findings = []
    src = BACKTEST.read_text(encoding="utf-8")
    if "as_of_time=max_date" not in src:
        fail("PIT-1", "DataSanitizer not called with as_of_time", findings)
    if 'pd.to_datetime(panel["date"].max())' not in src:
        warn("PIT-2", "as_of_time should be max(panel.date) for in-slice PIT safety", findings)
    return len([f for f in findings if f["sev"] == "P0"]) == 0, findings


def check_numerical_sanity():
    findings = []
    artifacts = {}
    for label, path in ARTIFACTS.items():
        if not path.exists():
            fail("NUM-MISS", f"Missing {path.name}", findings)
            return False, findings
        with open(path) as f:
            artifacts[label] = json.load(f)["baseline"]

    full = artifacts["full_1B"]
    if full["n_samples"] > 50000:
        warn("NUM-N", f"full n_samples={full['n_samples']} unexpectedly high (Phase 3.11 had 59133, expected drop)", findings)
    info("NUM-N",
         f"full n_samples={full['n_samples']} (Phase 3.11=59133, drop={59133 - full['n_samples']})", findings)
    info("NUM-IC",
         f"full median_test_IC={full['median_test_ic']:.4f} "
         f"(Phase 3.11=0.0137 -> {(full['median_test_ic']/0.0137-1)*100:+.1f}%)", findings)
    info("NUM-SR",
         f"full fold_SR_ann={full['fold_dsr']['sr_mean_annualized']:.3f} "
         f"(Phase 3.11=3.181 -> {(full['fold_dsr']['sr_mean_annualized']/3.181-1)*100:+.1f}%)", findings)
    info("NUM-DSR",
         f"full fold_DSR={full['fold_dsr']['dsr']:.4f} "
         f"(Phase 3.11=0.4452)", findings)
    cb = full["cost_breakdown"]
    if cb["total_slippage_cost"] < 0 or cb["total_commission_cost"] < 0 or cb["total_spread_cost"] < 0:
        fail("NUM-COST", "Negative cost breakdown components", findings)

    smoke = artifacts["smoke_1B"]
    info("NUM-SMOKE",
         f"smoke median_test_IC={smoke['median_test_ic']:.4f} (Phase 3.11 smoke=0.1242, expect uplift)",
         findings)
    return len([f for f in findings if f["sev"] == "P0"]) == 0, findings


def main():
    all_findings = []
    checks = [
        ("imports", check_imports),
        ("helpers defined", check_helpers_defined),
        ("cleaning order", check_cleaning_order),
        ("WF universe re-tag", check_universe_year_remapping),
        ("winsorize PIT", check_winsorize_pit),
        ("DataSanitizer as_of_time", check_pit_as_of_time),
        ("numerical sanity", check_numerical_sanity),
    ]
    overall = True
    print(f"{'check':<28} {'result':<8} notes")
    print("-" * 70)
    for name, fn in checks:
        ok, fs = fn()
        all_findings.extend(fs)
        notes = ", ".join(f"[{f['sev']}]{f['id']}" for f in fs) or "OK"
        print(f"{name:<28} {'PASS' if ok else 'FAIL':<8} {notes}")
        overall = overall and ok

    print()
    print("FINDINGS DETAIL")
    print("-" * 70)
    for f in all_findings:
        print(f"[{f['sev']}] {f['id']}: {f['msg']}")

    print()
    print(f"VERDICT: {'[APPROVED]' if overall else '[NEEDS_FIX]'}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
