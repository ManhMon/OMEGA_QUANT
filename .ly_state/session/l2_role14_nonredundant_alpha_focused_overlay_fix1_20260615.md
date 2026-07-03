# L2 Fix Report — NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615_FIX1

**GATE:** `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615_FIX1`
**Date:** 2026-06-15
**Role:** L2 Data Scientist (Role 14)
**L3 Audit Verdict:** [NEEDS_FIX] (Role 20 Compliance Officer)
**Status:** Fix Complete — Submitted for Tier 3 Re-Audit

---

## 1. L3 Audit Findings Addressed

| # | Finding | Fix Applied |
|---|---------|-------------|
| 1 | Evidence gate mismatch: `v1_mrm_only` and `v1_mrm_range` emitted `NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615` instead of `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` | Fixed gate routing in `phase35.py:3736-3744` |
| 2 | Missing regression tests for focused evidence gate | Added 6 new tests in `TestFocusedEvidenceGateRouting` class |
| 3 | Persisted JSON artifacts had wrong gate | Regenerated both focused overlay JSON artifacts |
| 4 | Phase gate entry absent in `phase_gates.json` | Out of L2 scope — L1 must seed the gate entry |

---

## 2. Files Modified

| File | Change | Lines |
|------|--------|-------|
| `src/omega/quant/alpha/phase35.py` | Fixed gate routing: added `elif` branch for `v1_mrm_only`/`v1_mrm_range` to use `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID` | 3736-3744 |
| `tests/phase35/test_nonredundant_alphas.py` | Added `TestFocusedEvidenceGateRouting` class (6 tests) | 1473-1628 |
| `data/phase35_results/phase35_backtest_results_v1_mrm_only_focused_overlay_baseline.json` | Regenerated: patched `nonredundant_alpha_evidence.gate` in all 12 folds | All folds |
| `data/phase35_results/phase35_backtest_results_v1_mrm_range_focused_overlay_baseline.json` | Regenerated: patched `nonredundant_alpha_evidence.gate` in all 12 folds | All folds |

### Files NOT Modified (Per Scope Constraints)

- `.ly_state/session/phase_gates.json` — Task constraint: "Do not modify phase_gates." L1 must seed the `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` gate entry.
- `src/omega/quant/alpha/nonredundant_alphas.py` — No changes needed. Gate constants and set registry are correct.
- `scripts/run_phase35_backtest.py` — No changes needed. CLI already supports focused overlay sets.

---

## 3. Fix Detail: Evidence Gate Routing

### Before (phase35.py:3736-3741)

```python
# Select gate ID based on set_name
_nr_gate_id = (
    NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID
    if self.nonredundant_alpha_set == "v1_pruned"
    else NONREDUNDANT_ALPHA_GATE_ID
)
```

**Bug:** `v1_mrm_only` and `v1_mrm_range` fell through to the `else` branch, emitting `NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615` instead of `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615`.

### After (phase35.py:3736-3744)

```python
# Select gate ID based on set_name
# GATE: NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615 — pruned gate
# GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615 — focused overlay gate
if self.nonredundant_alpha_set == "v1_pruned":
    _nr_gate_id = NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID
elif self.nonredundant_alpha_set in ("v1_mrm_only", "v1_mrm_range"):
    _nr_gate_id = NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID
else:
    _nr_gate_id = NONREDUNDANT_ALPHA_GATE_ID
```

### Gate Routing Matrix

| set_name | Gate ID (After Fix) |
|----------|---------------------|
| `v1` | `NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615` |
| `v1_pruned` | `NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615` |
| `v1_mrm_only` | `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` |
| `v1_mrm_range` | `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` |

---

## 4. New Tests Added

### TestFocusedEvidenceGateRouting (6 tests)

| Test | Assertion |
|------|-----------|
| `test_source_routes_focused_sets_to_focused_gate` | Source contains explicit routing for `v1_mrm_only`/`v1_mrm_range` to `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID` |
| `test_evidence_gate_for_v1_mrm_only` | Gate routing logic returns `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` for `v1_mrm_only` |
| `test_evidence_gate_for_v1_mrm_range` | Gate routing logic returns `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` for `v1_mrm_range` |
| `test_evidence_gate_for_v1_pruned_unchanged` | Gate routing logic still returns `NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615` for `v1_pruned` |
| `test_evidence_gate_for_v1_unchanged` | Gate routing logic still returns `NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615` for `v1` |
| `test_focused_overlay_json_artifacts_have_correct_gate` | Persisted JSON artifacts have `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` in all folds for both focused sets |

---

## 5. Test Results

```
pytest tests/phase35/test_nonredundant_alphas.py -v --tb=short
85 passed, 3 warnings in 6.85s
```

- **79 original tests**: All pass (unchanged)
- **6 new tests**: All pass (Section 15: TestFocusedEvidenceGateRouting)
- **Warnings**: 3 pre-existing (SQLAlchemy deprecation, discovery module deprecation, pytest cache path)

---

## 6. Preserved Invariants

| Invariant | Status |
|-----------|--------|
| Default off | PASS — `enable_nonredundant_alphas` defaults to `False` |
| Default set | PASS — `nonredundant_alpha_set` defaults to `"v1"` |
| PIT safety | PASS — No alpha computation changes; only metadata gate string fixed |
| phase_gates untouched | PASS — No modifications to `.ly_state/session/phase_gates.json` |
| v1 unchanged | PASS — 10 candidates, base gate routing preserved |
| v1_pruned unchanged | PASS — 5 candidates, pruned gate routing preserved |
| JSON serializable | PASS — Both patched JSON files parse correctly |
| Metrics unchanged | PASS — Only gate metadata string updated; all IC, Sharpe, MaxDD preserved |

---

## 7. Repo-Local Skill Evidence

| Source | Path |
|--------|------|
| Agent definition | `.agents/agent/data-scientist.md` |
| Skill: backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| Skill: testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| Skill: clean-code | `.agents/skills/clean-code/SKILL.md` |
| Skill: quant-research | `.agents/skills/quant-research/SKILL.md` |
| Skill: data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |
| Skill: systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| Skill: python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| L3 Audit report | `.ly_state/session/audit_reports/role20_nonredundant_alpha_focused_overlay_20260615.md` |
| L2 original report | `.ly_state/session/nonredundant_alpha_focused_overlay_report_20260615.md` |

---

## 8. Forbidden Path Scan

| Path | Status |
|------|--------|
| `.gemini\antigravity-ide\scratch\ag-kit` | Non-authoritative — NOT used as source |
| `.openclaw\skills` | Non-authoritative — NOT used as source |
| `C:\Users\GHC\.agents` | Non-authoritative — NOT used as source |
| `.codex\memories` | Non-authoritative — NOT used as source |

All source reads restricted to repo-local `.agents/agent/`, `.agents/skills/`, `src/`, `tests/`, `data/`, `scripts/`, and `.ly_state/session/`.

---

## 9. Scope Compliance

- **Implementation-only**: No audit or approval actions taken.
- **No self-approval**: Report submitted for Tier 3 re-audit.
- **No phase_gates modification**: Out of L2 scope per task constraint.
- **Test required**: 6 new regression tests added, all 85 tests pass.
- **No default behavior change**: Fix only affects opt-in focused overlay sets.

---

## 10. Remaining Action for L1

Per L3 audit finding #2: `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` must exist in `.ly_state/session/phase_gates.json` before L3 can update gate metadata. L1 must seed this entry in the next audit cycle.
