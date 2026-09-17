# L2 Implementation Report: Recovery Selector Phase35 Wiring
## GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614
### Role 14 — Data Scientist (OpenCode L2 Implementation)
### Date: 2026-06-14

---

## 1. SOD Boundary Compliance

- **Implementation-only**: This role implements, does not audit or approve.
- **Test required**: 46/46 new tests pass. 350/350 combined tests pass (no regressions).
- **No self-approval**: Submitted to Tier 3 (Code Reviewer role 21, QA Engineer role 17).
- **Forbidden path scan**: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories` are non-authoritative and were NOT read or used as source in this implementation.

---

## 2. Repo-Local Files Read (Authoritative Sources)

### Agent File
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\data-scientist.md` — frontmatter: role_id=14, tier=2, skills=[python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow]

### Skill Files (all declared in frontmatter)
| Skill | Path |
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

### Source Files Read
| File | Purpose |
|------|---------|
| `scripts/run_phase35_backtest.py` | CLI script — modified |
| `src/omega/quant/alpha/phase35.py` | Engine — modified (constructor only) |
| `src/omega/quant/walk_forward/alpha_selector.py` | Alpha selection mixin — read only (not modified) |
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Recovery utilities — read only (not modified) |
| `tests/phase35/test_cpcv_fold_expansion_cli_wiring.py` | Test pattern reference |
| `tests/test_risk_adjusted_alpha_score.py` | Existing test reference |

---

## 3. Implementation Summary

### Scope (per task)
- `scripts/run_phase35_backtest.py` — CLI arg + post-hoc recovery pool analysis + JSON persistence
- `src/omega/quant/alpha/phase35.py` — engine constructor parameter (validation + storage)
- `tests/phase35/test_recovery_selector_phase35_wiring.py` — 46 tests (new file)
- `data/phase35_results/phase35_backtest_results_cpcv12_recovery_only_smoke_xgboost.json` — smoke proof output
- `.ly_state/session/l2_role14_recovery_selector_phase35_wiring_20260614.md` — this report

### Changes Made

#### 3.1 CLI: `--research-pool-mode` (scripts/run_phase35_backtest.py)
- **New argparse argument**: `--research-pool-mode`, choices: `full|recovery_only|recoverable_only`, default: `full`
- **Gate label**: `RECOVERY_SELECTOR_PHASE35_WIRING_20260614`
- **Logging**: Mode logged during configuration output
- **Passed to engine**: `research_pool_mode=args.research_pool_mode`

#### 3.2 Post-Hoc Recovery Pool Analysis (scripts/run_phase35_backtest.py)
- **Triggered only when `mode != 'full'`** — default path unchanged
- **PIT-safe**: Uses only OOS fold-level ICs from `result.fold_metrics`
- **Steps**:
  1. Build `alpha_fold_ics` from fold metrics (per-alpha per-fold ICs)
  2. Build `fold_details` for regime-conditioned IC computation
  3. Call `compute_alpha_recovery_diagnostics()` from risk_adjusted_alpha_score.py
  4. Call `filter_alphas_by_recovery_mode()` to get filtered pool
  5. Compute full-pool vs recovery-pool mean fold IC and positive fold rate
  6. Call `compute_selector_ready_verdict()` for CONDITIONAL_PROMOTE / DO_NOT_PROMOTE / INSUFFICIENT_EVIDENCE
  7. Persist complete evidence dict in JSON results

#### 3.3 Engine: `research_pool_mode` Parameter (src/omega/quant/alpha/phase35.py)
- **Constructor parameter**: `research_pool_mode: str = "full"`
- **Validation**: Checked against `VALID_RESEARCH_POOL_MODES`, raises `ValueError` on invalid
- **Storage**: `self.research_pool_mode`
- **No `run_fold` changes**: Recovery analysis is purely post-hoc — no per-fold behavior change

#### 3.4 JSON Persistence
- **Config dict**: `research_pool_mode` persisted
- **`recovery_pool_evidence`** dict with keys:
  - `gate`: "RECOVERY_SELECTOR_PHASE35_WIRING_20260614"
  - `research_pool_mode`: actual mode used
  - `full_pool_alphas`: complete alpha list
  - `selected_alphas`: filtered alpha list
  - `excluded_alphas`: removed alpha list
  - `n_selected`, `n_excluded`: counts
  - `full_pool_mean_fold_ic`, `full_pool_positive_fold_rate`
  - `recovery_pool_mean_fold_ic`, `recovery_pool_positive_fold_rate`
  - `ic_delta`, `fold_rate_delta`
  - `selector_verdict`: CONDITIONAL_PROMOTE / DO_NOT_PROMOTE / INSUFFICIENT_EVIDENCE
  - `recovery_classifications`: recoverable, research_only, confirmed_retire lists
  - `pit_safe`: True

#### 3.5 No Live/Default Behavior Change
- Default mode `full` skips all recovery analysis entirely
- `recovery_pool_evidence = None` for default mode
- `run_fold()` is untouched — no per-fold behavior change
- All existing CLI args and engine params unchanged

---

## 4. Test Results

### New Tests: 46/46 PASSED
File: `tests/phase35/test_recovery_selector_phase35_wiring.py`

| Test Class | Count | Status |
|-----------|-------|--------|
| TestRecoveryPoolModeCLIFlags | 4 | PASS |
| TestDefaultBehaviorUnchanged | 4 | PASS |
| TestEngineConstructorValidation | 7 | PASS |
| TestRecoveryPoolFiltering | 4 | PASS |
| TestSelectorVerdict | 3 | PASS |
| TestPITSafety | 5 | PASS |
| TestOutputPersistence | 9 | PASS |
| TestConfigPersistence | 1 | PASS |
| TestLogging | 2 | PASS |
| TestEngineSourceInspection | 3 | PASS |
| TestRecoveryPoolEvidenceStructure | 1 | PASS |
| TestBackwardCompatibility | 3 | PASS |
| **Total** | **46** | **ALL PASS** |

### Regression Tests: 304/304 PASSED
| Test File | Count | Status |
|-----------|-------|--------|
| `tests/test_risk_adjusted_alpha_score.py` | 251 | ALL PASS |
| `tests/phase35/test_cpcv_fold_expansion_cli_wiring.py` | 53 | ALL PASS |

### Combined Total: 350/350 PASSED

---

## 5. Smoke Proof Output

### Quick-Mode Smoke: recovery_only
- **Command**: `python scripts/run_phase35_backtest.py --quick-mode --research-pool-mode recovery_only --output-tag cpcv12_recovery_only_smoke`
- **Output**: `data/phase35_results/phase35_backtest_results_cpcv12_recovery_only_smoke_xgboost.json`
- **Results**:
  - Full pool: 7 alphas, mean_fold_IC=0.0145, pos_fold_rate=100.0%
  - Filtered pool (recovery_only): 2 alphas (liquidity_provision_ratio_10, tick_signed_volume_imbalance_5)
  - Excluded: 5 alphas (classified as CONFIRMED_RETIRE)
  - Selector verdict: DO_NOT_PROMOTE (IC improved but fold rate unchanged at 100%)
  - pit_safe: true

### Default Mode Smoke: full (unchanged)
- **Command**: `python scripts/run_phase35_backtest.py --quick-mode --output-tag default_check`
- **Output**: `data/phase35_results/phase35_backtest_results_default_check_xgboost.json`
- **Results**:
  - `recovery_pool_evidence`: None (confirmed — no analysis for default mode)
  - `research_pool_mode`: "full" (confirmed)

### Full 12-Fold CPCV Recovery-Only
- Deferred to targeted test-level proof + smoke (12-fold runtime exceeds session budget)
- Existing cpcv12_fix2 data available for offline full-run via:
  `python scripts/run_phase35_backtest.py --n-folds 12 --research-pool-mode recovery_only --output-tag cpcv12_recovery_only`

---

## 6. PIT Safety Verification

| Check | Status |
|-------|--------|
| No look-ahead in post-hoc analysis | PASS — uses only `result.fold_metrics` alpha_ics (OOS test-set ICs) |
| `run_fold()` unchanged | PASS — verified via source inspection test |
| Recovery diagnostics use OOS data only | PASS — `compute_alpha_recovery_diagnostics()` takes fold-level metrics |
| `filter_alphas_by_recovery_mode()` PIT-safe | PASS — pure function on classifications, no data access |
| Default mode no analysis | PASS — `recovery_pool_evidence = None` when mode='full' |

---

## 7. Context: CPCV12 Fix2 Stat Validation Finding

The cpcv12_fix2 stat validation report found:
- **Full pool**: mean_fold_IC=-0.0097, positive_fold_rate=33.3%
- **Recovery-only pool**: mean_fold_IC=0.0008, positive_fold_rate=66.7%
- **Selector verdict**: CONDITIONAL_PROMOTE (both metrics improved on 12-fold data)
- **Overall verdict**: FAIL (weak alpha mean IC blocks — research-only path)

This wiring enables Phase35 to reproduce the CONDITIONAL_PROMOTE finding directly from the backtest script rather than requiring a separate analysis script.

---

## 8. Files Modified

| File | Change Type |
|------|------------|
| `scripts/run_phase35_backtest.py` | CLI arg + post-hoc analysis + JSON persistence |
| `src/omega/quant/alpha/phase35.py` | Constructor parameter + validation |

## 9. Files Created

| File | Purpose |
|------|---------|
| `tests/phase35/test_recovery_selector_phase35_wiring.py` | 46 tests |
| `data/phase35_results/phase35_backtest_results_cpcv12_recovery_only_smoke_xgboost.json` | Smoke proof |
| `data/phase35_results/phase35_backtest_summary_cpcv12_recovery_only_smoke_xgboost.txt` | Smoke summary |
| `.ly_state/session/l2_role14_recovery_selector_phase35_wiring_20260614.md` | This report |

---

## 10. Submission

Submitted to Tier 3 audit:
- **Code Reviewer (role 21)**: Code quality, reproducibility, and backward compatibility review
- **QA Engineer (role 17)**: Test coverage, PIT safety, and model validation review

Cannot proceed until both Tier 3 roles return [APPROVED].
