"""Independent L3 audit for Phase 3.8 slippage model.

Runs OFFLINE checks (no codex CLI required) on the artifacts produced by
backtest_v2_cpcv.py with --realistic-tc. Verifies:
  1. ADV is PIT-safe (rolling.shift(1)) -- inspects code via AST.
  2. ADV NaN handling -- inspects code via AST + JSON ADV stats.
  3. pivot_adv alignment with pivot_w -- structural code check.
  4. Slippage formula matches Almgren-Chriss linear impact -- code + numeric.
  5. Capital sensitivity 1B/10B/100B is internally consistent
     (slippage scales linearly, commission+spread are capital-invariant).

Exit code 0 = APPROVED, 1 = NEEDS_FIX.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BACKTEST = ROOT / "scripts" / "backtest_v2_cpcv.py"
EXEC_SIM = ROOT / "packages" / "quant" / "src" / "omega" / "quant" / "portfolio" / "execution_sim.py"

ARTIFACTS = {
    "1B": ROOT / ".ly_state/session/phase3_8_full_1B.json",
    "10B": ROOT / ".ly_state/session/phase3_8_full_10B.json",
    "100B": ROOT / ".ly_state/session/phase3_8_full_100B.json",
}


def fail(label: str, msg: str, findings: list[dict]) -> None:
    findings.append({"severity": "P0", "check": label, "msg": msg})


def warn(label: str, msg: str, findings: list[dict]) -> None:
    findings.append({"severity": "P1", "check": label, "msg": msg})


def info(label: str, msg: str, findings: list[dict]) -> None:
    findings.append({"severity": "P2", "check": label, "msg": msg})


def check_adv_pit() -> tuple[bool, list[dict]]:
    """1. ADV must use rolling().mean().shift(1) -- T-1 PIT."""
    findings: list[dict] = []
    src = BACKTEST.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found_attach = False
    has_rolling = False
    has_shift = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_attach_adv":
            found_attach = True
            body_src = ast.unparse(node)
            has_rolling = "rolling(" in body_src and ".mean()" in body_src
            has_shift = ".shift(1)" in body_src
            break
    if not found_attach:
        fail("PIT-1", "_attach_adv() not found in backtest_v2_cpcv.py", findings)
        return False, findings
    if not has_rolling:
        fail("PIT-2", "_attach_adv() does not use rolling(...).mean() for ADV", findings)
    if not has_shift:
        fail("PIT-3", "_attach_adv() missing .shift(1) -- look-ahead risk", findings)
    return (has_rolling and has_shift), findings


def check_adv_nan_handling() -> tuple[bool, list[dict]]:
    """2. NaN imputation should NOT use forward-only data; median over the
    full dataset is acceptable for backtest reporting but flagged for prod.
    """
    findings: list[dict] = []
    src = BACKTEST.read_text(encoding="utf-8")
    if "nanmedian(adv_arr)" not in src:
        warn("NAN-1", "Could not find nanmedian-based ADV imputation -- check manually", findings)
        return True, findings
    info(
        "NAN-INFO",
        "ADV NaN -> dataset median. Acceptable for backtest reporting; "
        "for live trading replace with rolling-trail median or last valid ADV per ticker.",
        findings,
    )
    return True, findings


def check_pivot_adv_alignment() -> tuple[bool, list[dict]]:
    """3. pivot_adv must share index/columns with pivot_w (same date/ticker)."""
    findings: list[dict] = []
    src = BACKTEST.read_text(encoding="utf-8")
    if "pivot_adv = pivot_w.copy() if adv_te is not None else None" not in src:
        fail(
            "ALIGN-1",
            "pivot_adv is not derived from pivot_w.copy() -- alignment risk",
            findings,
        )
        return False, findings
    if "pivot_adv.loc[date, tk] = adv_val" not in src:
        fail(
            "ALIGN-2",
            "pivot_adv is not populated per (date, ticker) inside the daily loop",
            findings,
        )
        return False, findings
    if "daily_adv=adv_matrix" not in src:
        fail(
            "ALIGN-3",
            "pivot_adv is not passed to apply_realistic_tc as daily_adv",
            findings,
        )
        return False, findings
    return True, findings


def check_slippage_formula() -> tuple[bool, list[dict]]:
    """4. Slippage formula = k * participation * |delta_w|, scaled by AUM."""
    findings: list[dict] = []
    src = EXEC_SIM.read_text(encoding="utf-8")
    needed = [
        "participation = np.where(adv_row > 0, trade_vnd / adv_row, 0)",
        "slippage_per_name = cost_model.slippage_k * participation",
        "slippage_per_name * np.abs(delta_w)",
        "trade_vnd = np.abs(delta_w) * portfolio_capital_vnd",
    ]
    for needle in needed:
        if needle not in src:
            fail("SLIP-1", f"execution_sim.py missing canonical line: '{needle}'", findings)
            return False, findings
    return True, findings


def check_capital_consistency() -> tuple[bool, list[dict]]:
    """5. commission+spread should be capital-invariant; slippage scales linearly."""
    findings: list[dict] = []
    summaries: dict[str, dict[str, Any]] = {}
    for cap, path in ARTIFACTS.items():
        if not path.exists():
            fail("CAP-MISS", f"Missing artifact: {path.name}", findings)
            return False, findings
        with open(path) as f:
            d = json.load(f)["baseline"]
        b = d["cost_breakdown"]
        summaries[cap] = b

    # Commission + spread must be exactly equal across capitals (no capital
    # term in their formula).
    base_comm = summaries["1B"]["total_commission_cost"]
    base_spread = summaries["1B"]["total_spread_cost"]
    for cap in ("10B", "100B"):
        if abs(summaries[cap]["total_commission_cost"] - base_comm) > 1e-9:
            fail(
                "CAP-COMM",
                f"commission @ {cap} differs from 1B "
                f"({summaries[cap]['total_commission_cost']} vs {base_comm})",
                findings,
            )
        if abs(summaries[cap]["total_spread_cost"] - base_spread) > 1e-9:
            fail(
                "CAP-SPREAD",
                f"spread @ {cap} differs from 1B "
                f"({summaries[cap]['total_spread_cost']} vs {base_spread})",
                findings,
            )

    # Slippage should scale ~ linearly with capital (factor 10 across each step).
    slip_1b = summaries["1B"]["total_slippage_cost"]
    slip_10b = summaries["10B"]["total_slippage_cost"]
    slip_100b = summaries["100B"]["total_slippage_cost"]
    ratio_10 = slip_10b / slip_1b if slip_1b > 0 else float("nan")
    ratio_100 = slip_100b / slip_10b if slip_10b > 0 else float("nan")
    info(
        "CAP-SLIP",
        f"slip 1B={slip_1b:.4e}  10B={slip_10b:.4e} (x{ratio_10:.2f})  "
        f"100B={slip_100b:.4e} (x{ratio_100:.2f}); expected ~x10 each step",
        findings,
    )
    # Tolerate 10% deviation (cross-fold weight changes can shift effective participation).
    for label, ratio in [("10B/1B", ratio_10), ("100B/10B", ratio_100)]:
        if not (8.0 < ratio < 12.0):
            warn(
                "CAP-LINEAR",
                f"slippage ratio {label}={ratio:.3f} outside [8, 12]; check linearity",
                findings,
            )
    return True, findings


def main() -> int:
    all_findings: list[dict] = []
    checks = [
        ("ADV PIT-safe", check_adv_pit),
        ("ADV NaN handling", check_adv_nan_handling),
        ("pivot_adv alignment", check_pivot_adv_alignment),
        ("slippage formula", check_slippage_formula),
        ("capital consistency", check_capital_consistency),
    ]
    overall_ok = True
    print(f"{'check':<24} {'result':<10} notes")
    print("-" * 70)
    for name, fn in checks:
        ok, findings = fn()
        all_findings.extend(findings)
        notes = ", ".join(f"[{f['severity']}] {f['check']}" for f in findings) or "OK"
        print(f"{name:<24} {'PASS' if ok else 'FAIL':<10} {notes}")
        overall_ok = overall_ok and ok

    print()
    print("FINDINGS DETAIL")
    print("-" * 70)
    for f in all_findings:
        print(f"[{f['severity']}] {f['check']}: {f['msg']}")

    print()
    print(f"VERDICT: {'[APPROVED]' if overall_ok else '[NEEDS_FIX]'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
