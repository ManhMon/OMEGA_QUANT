# L2 Report — HYBRID_REGIME_BACKTEST_PERF_20260621

**L2 session ID**: `l2_role14_tcost_rebalance_opt_fix_20260622`
**Role**: 14 `data-scientist` (tier=2, platform=OpenCode, sod_boundary=implementation-only)
**Gate**: `HYBRID_REGIME_BACKTEST_PERF_20260621`
**Date**: 2026-06-22
**Repo-local**: `C:\Users\GHC\repos\OMEGA_QUANT`

---

## 1. Repo-Local Skill Source Evidence (STRICT_REPO_LOCAL_SKILL_LOADING_20260612)

### Role spec read
- `REPO_AGENT_ROOT/data-scientist.md` (role_id=14, tier=2, platform=OpenCode, sod_boundary=implementation-only)
- `.agents/agent/data-scientist.md` (full repo-relative path; same file as above, listed verbatim per enforcer contract)

### Skills declared in role frontmatter (loaded only required ones for this task)
Read directly from `.agents/skills/<skill_name>/SKILL.md`:

| Skill | Path | Relevant for this task |
|-------|------|------------------------|
| `testing-patterns` | `.agents/skills/testing-patterns/SKILL.md` | Yes — AAA pattern, One assert per test, Independent tests |
| `python-patterns` | `.agents/skills/python-patterns/SKILL.md` | Yes — DRY, guard clauses |
| `clean-code` | `.agents/skills/clean-code/SKILL.md` | Yes — KISS, Boy Scout, remove unused code |
| `backtesting-pit-safety` | `.agents/skills/backtesting-pit-safety/SKILL.md` | Yes — Cost-adjusted metrics, no in-sample trust |
| `quant-research` | `.agents/skills/quant-research/SKILL.md` | Yes — Cost-adjusted evaluation, net-of-cost IC |

Skills declared in frontmatter but NOT loaded (not required for surgical assertion rewrite):
`systematic-debugging`, `performance-profiling`, `vietnam-market-data`, `data-science-workflow`.

### Forbidden path scan
Result: **PASS** — no authoritative skill/role source loaded from any forbidden path.

| Forbidden Path | Scanned | Result |
|----------------|---------|--------|
| `.gemini\antigravity-ide\scratch\ag-kit` | yes | NOT used (non-authoritative) |
| `.openclaw\skills` | yes | NOT used (non-authoritative) |
| `C:\Users\GHC\.agents` | yes | NOT used (non-authoritative) |
| `.codex\memories` | yes | NOT used (non-authoritative) |

All skill reads came from `REPO_SKILL_ROOT = C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.

---

## 2. Task

Modify `test_realized_alpha_improvement_from_backtest` (in `tests/phase35/test_hybrid_regime_alpha_improvement.py`) to validate:
1. **Net Return improvement**: `hy_net_pct > bl_net_pct`
2. **Transaction Cost reduction**: `hy_tc_pct < bl_tc_pct`

…instead of the previous gross-return-dominance contract (`hy_gross_pct > bl_gross_pct` and `hy_gross_pct > 8.76%` target). Verify all phase35 tests pass.

---

## 3. Scope

**File modified** (single, surgical edit):
- `tests/phase35/test_hybrid_regime_alpha_improvement.py` — only `TestDiagnosticJSON.test_realized_alpha_improvement_from_backtest`

No production source code, scripts, or other tests were touched (SOD: L2 implementation-only).

---

## 4. Implementation

### Diff summary

The method `test_realized_alpha_improvement_from_backtest` was rewritten in-place. The change set is bounded:

| Section | Before | After |
|---------|--------|-------|
| Docstring "Asserts:" | Gross return dominance | Net return improvement + TC reduction |
| Summary field extraction | 8 fields (incl. `improvement_gross_pct`, `target_pct`) | 4 fields (only `bl_net_pct`, `hy_net_pct`, `bl_tc_pct`, `hy_tc_pct`) |
| None-safety checks | 2 (gross fields only) | 4 (net + tc fields) |
| Assertion 1 | `hy_gross_pct > bl_gross_pct` | `hy_net_pct > bl_net_pct` |
| Assertion 2 | `hy_gross_pct > target_pct` (8.76% target) | `hy_tc_pct < bl_tc_pct` |
| Assertions 3 & 4 (per-fold, alpha columns) | unchanged | unchanged |

### Key assertion code (after)

```python
assert hy_net_pct > bl_net_pct, (
    f"REALIZED hybrid net ({hy_net_pct:.2f}%) does not exceed "
    f"baseline net ({bl_net_pct:.2f}%). "
    f"Net improvement: {net_improvement_pct:+.2f}%"
)

assert hy_tc_pct < bl_tc_pct, (
    f"REALIZED hybrid TC ({hy_tc_pct:.2f}%) is not below "
    f"baseline TC ({bl_tc_pct:.2f}%). "
    f"TC reduction: {tc_reduction_pct:.2f}%"
)
```

### Design rationale (per quant-research / backtesting-pit-skill)

- **Net of cost > gross**: Per `backtesting-pit-safety/SKILL.md` §6 and `quant-research/SKILL.md` §3, deployability is governed by **net returns** (gross − transaction cost). A strategy with lower gross but materially lower TC can be more deployable.
- **TC reduction as primary signal**: Regime-aware rebalancing reduces turnover. The realized delta in `mean_tc_pct` is the direct measure of this improvement. Comparing hybrid vs baseline TC is the correct test for the "regime-aware rebalance optimization" thesis behind this gate.
- **Direction of inequality**: Net must strictly improve (`>`); TC must strictly reduce (`<`). Equality is treated as failure (no value-add).
- **Removed unused variables**: `improvement_gross_pct`, `target_pct`, `bl_gross_pct`, `hy_gross_pct` were extracted but no longer used in any assertion. Removed per clean-code KISS/Boy Scout principle.

### PIT-safety compliance

Test still verifies:
- `data["measurement_type"] == "REALIZED_45_FOLD_CPCV"` — real backtest, not projection
- `data["pit_safe"] is True` — T-1 lag verified upstream
- Per-fold arrays present with `n_folds >= 10` — sufficient statistical mass

No change to PIT-safety invariants.

---

## 5. Test Execution

### Targeted test
```
$ python -m pytest tests/phase35/test_hybrid_regime_alpha_improvement.py::TestDiagnosticJSON::test_realized_alpha_improvement_from_backtest -v
tests\phase35\test_hybrid_regime_alpha_improvement.py .  [100%]
1 passed, 4 warnings in 6.11s
```

### Full phase35 file (regression check)
```
$ python -m pytest tests/phase35/test_hybrid_regime_alpha_improvement.py -v
tests\phase35\test_hybrid_regime_alpha_improvement.py .................. [ 69%]
........                                                                 [100%]
26 passed, 4 warnings in 6.71s
```

All 26 tests in the file pass. No regressions.

### Verification against current realized JSON

Latest `data/phase35_results/alpha_improvement_real_20260622_233553.json` summary:

| Metric | Baseline | Hybrid | New assertion | Result |
|--------|----------|--------|---------------|--------|
| Mean net return (%) | -45.78 | -7.74 | `hy_net > bl_net` | PASS (-7.74 > -45.78) |
| Mean transaction cost (%) | 88.60 | 9.76 | `hy_tc < bl_tc` | PASS (9.76 < 88.60) |

Realized improvements:
- **Net return**: +38.04 pp
- **TC reduction**: -78.84 pp

The regime-aware system delivers both stronger net return AND materially lower transaction cost.

---

## 6. SOD Boundary Compliance

| Rule | Status |
|------|--------|
| Writer != Auditor | PASS — L2 (role 14) wrote, L3 (role 21 or 17) will audit |
| L2 implementation-only | PASS — only `tests/phase35/...` touched |
| No production source code changes | PASS |
| No L3 write boundary violations | PASS — no writes to `.ly_state/session/audit_reports/` |
| Repo-local skill sources only | PASS — see §1 |
| PIT safety preserved | PASS — assertions still gate on `pit_safe=True` and `REALIZED_45_FOLD_CPCV` |
| L2 report naming | PASS — `l2_role14_tcost_rebalance_opt_fix_20260622.md` |

---

## 7. Stop Conditions

None triggered. All required repo-local sources present and readable. Test passes. Ready for L3 audit.

---

## 8. Files Modified (Authoritative)

- `tests/phase35/test_hybrid_regime_alpha_improvement.py` — single test method `test_realized_alpha_improvement_from_backtest` (lines 437-524)

No other files modified.
