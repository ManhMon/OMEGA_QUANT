# L2 Implementation Report — CPCV Fold Expansion Fix1

**GATE:** `CPCV_FOLD_EXPANSION_FIX1_20260614`
**Role:** 14 Data Scientist (Tier 2, OpenCode L2)
**Date:** 2026-06-14
**Status:** IMPLEMENTED — submitted to Tier 3 audit

---

## 1. Defect Summary

| Field | Value |
|-------|-------|
| **Reported behavior** | `--n-folds 12` accepted, `[CPCV_FOLD_EXPANSION] n_folds=12` logged, but output JSON has `config.n_folds=8` and summary shows 8 folds |
| **Reproduction** | `data/phase35_results/phase35_backtest_results_cpcv12_xgboost.json` |
| **Severity** | Medium — misleading persisted config, no PIT violation |

### Observed Defect Evidence (cpcv12 output)

```json
{
  "config": {
    "n_folds": 8,
    "cpcv_fold_expansion_n_folds": 12
  },
  "summary": {
    "total_folds": 8
  }
}
```

`config.n_folds` is 8 despite `--n-folds 12` being requested. `cpcv_fold_expansion_n_folds` correctly shows 12 (requested), but `config.n_folds` — the primary field consumers read — shows 8.

---

## 2. Root Cause Analysis (Systematic Debugging)

### Phase 1: Reproduce

Confirmed via persisted JSON file inspection.

### Phase 2: Isolate

Two independent root causes:

**Root Cause A — Fixed 365-day step in `create_walk_forward_splits`:**
- `Phase35DataLoader.create_walk_forward_splits()` used a **hardcoded step of 365 days** between consecutive folds.
- With `n_folds=12`, `train_years=3`, `test_years=1`, the last fold's `test_end` exceeded `max_date` after only 8 folds.
- Formula: `test_end = min_date + fold_idx*365 + 3*365 + 1*365`. For fold_idx=8: `2015 + 12*365 ≈ 2027 > 2026-05-14`.

**Root Cause B — Config persisted `len(splits)` instead of `N_FOLDS`:**
- Line 458 of `run_phase35_backtest.py`: `"n_folds": len(splits)` — persisted the actual count (8), not the CLI-requested value (12).
- This masked the discrepancy: the CLI asked for 12, the config said 8.

### Phase 3: Understand

The 5 Whys:
1. Why only 8 folds? → Step size of 365 days runs out of data before 12 folds.
2. Why 365-day step? → Hardcoded, not parameterized by `n_folds`.
3. Why not parameterized? → Original implementation assumed fixed yearly cadence.
4. Why does config show 8? → `"n_folds": len(splits)` persisted actual, not requested.
5. Why no warning? → No mismatch detection between requested and actual fold count.

### Phase 4: Fix & Verify

See Section 3 below.

---

## 3. Surgical Fix Implementation

### Files Modified

| File | Change | Lines |
|------|--------|-------|
| `scripts/phase35_data_loader.py` | Adaptive step size in `create_walk_forward_splits` | 240-332 |
| `scripts/run_phase35_backtest.py` | Config/summary persistence fix + warning | 404-411, 467-468, 509-510 |
| `tests/phase35/test_cpcv_fold_expansion_cli_wiring.py` | Added FIX1 test classes | Full rewrite |

### Fix A: Adaptive Step Size (`phase35_data_loader.py`)

**Before:** `train_start = min_date + fold_idx * 365` (hardcoded step)

**After:**
```python
legacy_step = 365
available_span = total_days - train_window_days - test_window_days
if n_folds > 1 and available_span > 0:
    max_step = available_span // (n_folds - 1)
    step_days = min(legacy_step, max_step)
else:
    step_days = legacy_step
step_days = max(step_days, 1)
```

**Backward compatibility:** `min(365, max_step)` ensures:
- Default 8 folds with 12yr data: `max_step = 2675/7 = 382 > 365` → step stays 365 ✓
- 12 folds with 12yr data: `max_step = 2675/11 = 243 < 365` → step shrinks to 243 ✓
- Quick-mode 2 folds: `max_step` very large → step stays 365 ✓

### Fix B: Config/Summary Persistence (`run_phase35_backtest.py`)

| Field | Before | After |
|-------|--------|-------|
| `config.n_folds` | `len(splits)` (actual) | `N_FOLDS` (requested) |
| `config.n_folds_executed` | (missing) | `len(splits)` (actual) |
| `summary.n_folds_requested` | (missing) | `N_FOLDS` (requested) |
| Warning on mismatch | (missing) | Logged when `n_folds_executed < N_FOLDS` |

---

## 4. Test Results

### Targeted Tests (53 tests)

```
tests/phase35/test_cpcv_fold_expansion_cli_wiring.py ... 53 passed
```

New test classes added:
- `TestCPCVFoldExpansionFix1PersistedNFolds` (5 tests) — verifies config/summary field correctness
- `TestCPCVFoldExpansionFix1AdaptiveStep` (7 tests) — verifies adaptive step produces requested folds
- `TestCPCVFoldExpansionFix1EndToEndConsistency` (3 tests) — regression guards

### Full Phase35 Suite (226 tests)

```
tests/phase35/ ... 226 passed, 0 failed
```

### Smoke Proof (synthetic data, real date range 2015-2026)

| Configuration | Before Fix | After Fix |
|---------------|-----------|-----------|
| `--n-folds 8 --train-years 3 --test-years 1` | 8 folds | 8 folds (unchanged) |
| `--n-folds 12 --train-years 3 --test-years 1` | **8 folds** (defect) | **12 folds** (fixed) |
| `--n-folds 2 --train-years 1 --test-years 1` | 2 folds | 2 folds (unchanged) |

All folds verified PIT-safe: `test_start > train_end` for every fold.

---

## 5. Agent / Skill Files Read

### Repo-Local Agent File
- `.agents/agent/data-scientist.md` — role_id=14, tier=2, platform=OpenCode

### Repo-Local Skill Files (from `.agents/skills/`)
| Skill | File |
|-------|------|
| python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| clean-code | `.agents/skills/clean-code/SKILL.md` |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| performance-profiling | `.agents/skills/performance-profiling/SKILL.md` |
| quant-research | `.agents/skills/quant-research/SKILL.md` |
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |

### Forbidden Path Scan
- **No** files read from `C:\Users\GHC\.agents\` (Antigravity/OpenClaw/Codex memory)
- **No** files read from scratch or unauthorized locations
- All reads from `REPO_AGENT_ROOT` and `REPO_SKILL_ROOT` only

---

## 6. Scope Compliance

| Item | Status |
|------|--------|
| Only `scripts/run_phase35_backtest.py` modified | ✓ |
| Only `scripts/phase35_data_loader.py` modified (narrow root cause) | ✓ |
| Only `tests/phase35/test_cpcv_fold_expansion_cli_wiring.py` modified | ✓ |
| L2 report written to `.ly_state/session/` | ✓ |
| No self-approval (Tier 3 audit required) | ✓ |
| Default behavior unchanged (8/3/1/30) | ✓ |
| Quick-mode unchanged (2/1/1/1) | ✓ |
| PIT safety preserved | ✓ |

---

## 7. Submission to Tier 3

This implementation is submitted for audit to:
- **Code Reviewer (role 21):** Code quality, backward compatibility, clean-code standards
- **QA Engineer (role 17):** Test coverage, regression guards, PIT safety verification

**Cannot proceed to live deployment until both return `[APPROVED]`.**
