# L2 Fix Report: DYNAMIC_REBALANCE_UNIVERSE_20260615_FIX1

**Role**: 14 — Data Scientist (L2 Implementation)
**Gate**: DYNAMIC_REBALANCE_UNIVERSE_20260615_FIX1
**Date**: 2026-06-15
**Status**: FIXED — resubmitting to Tier 3 audit
**Prior verdict**: [NEEDS_FIX] from Compliance Officer (Role 20)

---

## 1. Blockers Addressed

### Blocker 1: Per-Fold Dynamic Universe Evidence Never Attached

**Root cause**: `FoldMetrics` was constructed at `phase35.py:3179-3204` without passing
`dynamic_universe_evidence`, even though the field existed and `serialize_fold_details`
persisted it. Result: `fold_details[*].dynamic_universe_evidence` was absent.

**Fix**:
1. Added `_build_fold_dynamic_universe_evidence(test_df)` method to
   `Phase35WalkForwardEngine` that collects per-fold schedule usage stats
   (exact entries, carry-forward dates, schedule size, PIT safety flag).
2. Called it in `run_fold` after `_apply_stage2_constraints` and stored the
   result as `_dynamic_universe_evidence`.
3. Passed `dynamic_universe_evidence=_dynamic_universe_evidence` to the
   `FoldMetrics` constructor.
4. Added 5 tests proving:
   - Evidence dict is non-None when dynamic universe is enabled
   - Evidence dict is None when dynamic universe is disabled
   - `FoldMetrics` carries the evidence field
   - `serialize_fold_details` persists the evidence to JSON
   - None evidence is omitted from serialized output

### Blocker 2: Unsafe Cross-Fold Carry-Forward State

**Root cause**: `_last_dyn_universe` was stored on `self` (the engine instance) at
`phase35.py:1894-1901`. `run_walk_forward` reuses the same engine across all folds
(`phase35.py:3241-3243`). A later date from fold N could be carried into an earlier
date in fold N+1, violating PIT safety.

**Fix**:
1. Removed all `_last_dyn_universe` read/write from `_apply_stage2_constraints`.
2. Added `_lookup_latest_dyn_universe_up_to(date_str)` — a pure, stateless method
   that scans the immutable `dynamic_universe_schedule` dict for the latest key
   strictly <= the query date. No instance state is consulted or mutated.
3. Replaced carry-forward logic with calls to `_lookup_latest_dyn_universe_up_to`.
4. Added defensive `del self._last_dyn_universe` at fold start in `run_fold` to
   clear any stale attribute from prior versions.
5. Removed dead `_dyn_applied` assignments.
6. Added 7 tests proving:
   - Lookup returns None for dates before all schedule entries
   - Lookup returns exact match when present
   - Lookup returns latest entry strictly before query date
   - **Regression**: later schedule entry from fold N cannot leak into fold N+1
   - **Regression**: even if `_last_dyn_universe` is set manually, lookup ignores it
   - Empty and None schedules return None
   - `_apply_stage2_constraints` does not persist `_last_dyn_universe`

## 2. Files Changed

| File | Change |
|------|--------|
| `src/omega/quant/alpha/phase35.py` | Added `_lookup_latest_dyn_universe_up_to` and `_build_fold_dynamic_universe_evidence` methods; replaced `_last_dyn_universe` carry-forward with pure date-safe lookup; added defensive reset in `run_fold`; passed evidence to `FoldMetrics`; removed dead `_dyn_applied` |
| `tests/phase35/test_phase35_dynamic_universe.py` | Added `TestPerFoldDynamicUniverseEvidence` (5 tests) and `TestCrossFoldCarryForwardSafety` (7 tests) |

No changes to `scripts/run_phase35_backtest.py` — serializer already wired correctly.

## 3. Code Changes Detail

### 3.1 `_lookup_latest_dyn_universe_up_to(date_str)` (phase35.py)

```python
def _lookup_latest_dyn_universe_up_to(self, date_str):
    """Pure date-safe lookup: latest schedule key <= date_str.
    No instance state consulted. No side effects."""
    if not self.dynamic_universe_schedule:
        return None
    target = pd.Timestamp(date_str)
    best_key = None
    for sched_key in self.dynamic_universe_schedule:
        sched_ts = pd.Timestamp(sched_key)
        if sched_ts <= target:
            if best_key is None or sched_ts > pd.Timestamp(best_key):
                best_key = sched_key
    if best_key is not None:
        return self.dynamic_universe_schedule[best_key]
    return None
```

### 3.2 `_build_fold_dynamic_universe_evidence(test_df)` (phase35.py)

Returns per-fold evidence dict with:
- `gate`, `enabled`, `schedule_size`, `pit_safe`
- `n_test_dates_with_exact_entry` — dates matching schedule keys
- `n_test_dates_with_carry_forward` — dates using latest-prior lookup
- `rebalance_dates_in_fold` — first 10 exact-match dates
- `carry_forward_dates_sample` — first 5 carry-forward dates

Returns `None` when dynamic universe is disabled.

### 3.3 Stage 2 Carry-Forward Replacement

Before (unsafe):
```python
if hasattr(self, '_last_dyn_universe') and self._last_dyn_universe:
    alpha_row = alpha_row[alpha_row.index.isin(self._last_dyn_universe)]
# ...
self._last_dyn_universe = list(eligible)
```

After (pure functional):
```python
_carry_eligible = self._lookup_latest_dyn_universe_up_to(date_str)
if _carry_eligible is not None:
    alpha_row = alpha_row[alpha_row.index.isin(set(_carry_eligible))]
```

## 4. Test Results

### 4.1 Focused Tests (test_phase35_dynamic_universe.py)

```
46 passed, 0 failed (7.30s)
```

New test classes:
- `TestPerFoldDynamicUniverseEvidence` (5 tests): evidence built, persisted, serializable
- `TestCrossFoldCarryForwardSafety` (7 tests): pure lookup, no cross-fold leakage

### 4.2 Regression Tests (all phase35 tests)

```
619 passed, 0 failed (23.26s)
```

No regressions. Previous baseline: 607 passed. Added 12 new tests (5 + 7).

## 5. Preserved Invariants

| Invariant | Status |
|-----------|--------|
| Dynamic universe default OFF | Preserved — `dynamic_universe_schedule=None` by default |
| PIT selection_end < rebalance_date | Preserved — unchanged in `DynamicUniverseSelector` |
| JSON-serializable evidence | Preserved — per-fold evidence dict is all-primitive |
| No eval/exec/pickle/secrets | Preserved — no new unsafe patterns |
| `serialize_fold_details` backward compatible | Preserved — `getattr(m, "dynamic_universe_evidence", None)` |

## 6. Repo-Local Source Files Read

| Path | Purpose |
|------|---------|
| `.agents/agent/data-scientist.md` | Role definition (role 14, tier 2, platform OpenCode) |
| `.agents/skills/python-patterns/SKILL.md` | Python patterns skill |
| `.agents/skills/clean-code/SKILL.md` | Clean code standards |
| `.agents/skills/testing-patterns/SKILL.md` | Testing patterns |
| `.agents/skills/systematic-debugging/SKILL.md` | 4-phase debugging methodology |
| `.agents/skills/performance-profiling/SKILL.md` | Performance profiling |
| `.agents/skills/quant-research/SKILL.md` | Quant research / alpha lifecycle |
| `.agents/skills/vietnam-market-data/SKILL.md` | VN market data / VND_FULL scale |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | PIT safety / walk-forward / CPCV |
| `.agents/skills/data-science-workflow/SKILL.md` | Data science workflow / reproducibility |
| `.ly_state/session/audit_reports/role20_dynamic_rebalance_universe_20260615.md` | L3 audit report with blockers |
| `.ly_state/session/l2_role14_dynamic_rebalance_universe_20260615.md` | Original L2 report |
| `src/omega/quant/alpha/phase35.py` | Primary source file (all changes) |
| `scripts/run_phase35_backtest.py` | Serializer verification (no changes needed) |
| `tests/phase35/test_phase35_dynamic_universe.py` | Test file (new tests added) |

## 7. Forbidden Path Scan Result

No authoritative reliance on forbidden paths:
- `.gemini\antigravity-ide\scratch\ag-kit` — non-authoritative, not used as source
- `.openclaw\skills` — non-authoritative, not used as source
- `C:\Users\GHC\.agents` — non-authoritative, not used as source
- `.codex\memories` — non-authoritative, not used as source

## 8. Metrics

| Metric | Value |
|--------|-------|
| Files changed | 2 (phase35.py, test file) |
| Tests added | 12 (5 per-fold evidence + 7 cross-fold safety) |
| Total focused tests | 46 (was 34) |
| Total phase35 tests passing | 619/619 (was 607/607) |
| Blockers fixed | 2/2 |
| PIT violations | 0 |
| Regressions | 0 |

---

**Tier 3 Audit Resubmission**: This fix is resubmitted to Code Reviewer (role 21)
and Compliance Officer (role 20) for re-audit under gate
DYNAMIC_REBALANCE_UNIVERSE_20260615_FIX1. Cannot proceed until both return [APPROVED].
