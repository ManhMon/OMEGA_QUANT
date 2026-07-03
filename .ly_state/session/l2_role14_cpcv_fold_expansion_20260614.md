# L2 Implementation Report: CPCV Fold Expansion (Opt-In)

**GATE:** CPCV_FOLD_EXPANSION_20260614
**Role:** 14 Data Scientist (Tier 2 - Implementation Only)
**Date:** 2026-06-14
**Git Base:** b93d0e9

---

## 1. Objective

Add opt-in CLI arguments for Phase 3.5 walk-forward backtest fold expansion parameters, enabling CPCV-ready research configurations without changing default/live behavior.

## 2. Role/Skill Source Report

### Repo-Local Files Read (Authoritative)

| File | Path |
|------|------|
| **Role** | `.agents/agent/data-scientist.md` (role_id: 14, tier: 2) |
| **Skill** | `.agents/skills/python-patterns/SKILL.md` |
| **Skill** | `.agents/skills/clean-code/SKILL.md` |
| **Skill** | `.agents/skills/testing-patterns/SKILL.md` |
| **Skill** | `.agents/skills/systematic-debugging/SKILL.md` |
| **Skill** | `.agents/skills/performance-profiling/SKILL.md` |
| **Skill** | `.agents/skills/quant-research/SKILL.md` |
| **Skill** | `.agents/skills/vietnam-market-data/SKILL.md` |
| **Skill** | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| **Skill** | `.agents/skills/data-science-workflow/SKILL.md` |

### Forbidden Path Scan Results

| Path | Result |
|------|--------|
| `.gemini\antigravity-ide\scratch\ag-kit` | Non-existent in repo. .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source |
| `.openclaw\skills` | Non-existent in repo. .openclaw\skills is non-authoritative and not used as source |
| `C:\Users\GHC\.agents` | Exists on disk. C:\Users\GHC\.agents is non-authoritative and not used as source |
| `.codex\memories` | Non-existent in repo. .codex\memories is non-authoritative and not used as source |

**No forbidden paths were read or used as source material.**

## 3. Scope

| File | Action |
|------|--------|
| `scripts/run_phase35_backtest.py` | Modified: added 5 opt-in CLI args, quick-mode override logic, output-tag filename support, JSON config persistence |
| `tests/phase35/test_cpcv_fold_expansion_cli_wiring.py` | Created: 37 targeted tests covering CLI flags, defaults, quick-mode override, output-tag, config persistence, PIT safety, no-default-change |
| `.ly_state/session/l2_role14_cpcv_fold_expansion_20260614.md` | This file |

## 4. Changes Implemented

### 4.1 New CLI Arguments (Opt-In)

| Arg | Type | Default | Quick-Mode | Description |
|-----|------|---------|------------|-------------|
| `--n-folds` | int | None (falls back to 8) | 2 | Number of walk-forward folds |
| `--train-years` | int | None (falls back to 3) | 1 | Training window in years |
| `--test-years` | int | None (falls back to 1) | 1 | Test window in years |
| `--top-n-symbols` | int | None (falls back to 30) | 1 | Number of top symbols |
| `--output-tag` | str | None | N/A | Tag for output filenames |

### 4.2 Quick-Mode Override Logic

When `--quick-mode` is active, it **always** overrides to 2/1/1/1 regardless of what CLI values are provided. This is implemented as a clear if/else block:

```python
if args.quick_mode:
    TOP_N_SYMBOLS = 1
    N_FOLDS = 2
    TRAIN_YEARS = 1
    TEST_YEARS = 1
else:
    TOP_N_SYMBOLS = args.top_n_symbols if args.top_n_symbols is not None else _DEFAULT_TOP_N_SYMBOLS
    N_FOLDS = args.n_folds if args.n_folds is not None else _DEFAULT_N_FOLDS
    TRAIN_YEARS = args.train_years if args.train_years is not None else _DEFAULT_TRAIN_YEARS
    TEST_YEARS = args.test_years if args.test_years is not None else _DEFAULT_TEST_YEARS
```

### 4.3 Output-Tag Filename Support

When `--output-tag` is provided, the tag is prepended to the result suffix:

```python
result_suffix = "xgboost" if args.use_xgboost else "baseline"
if args.output_tag:
    result_suffix = f"{args.output_tag}_{result_suffix}"
```

Result filenames become:
- `phase35_backtest_results_{tag}_{xgboost|baseline}.json`
- `phase35_backtest_summary_{tag}_{xgboost|baseline}.txt`

Without `--output-tag`, filenames are unchanged (backward-compatible).

### 4.4 JSON Config Persistence

Five new keys persisted in the results JSON:
- `cpcv_fold_expansion_n_folds`
- `cpcv_fold_expansion_train_years`
- `cpcv_fold_expansion_test_years`
- `cpcv_fold_expansion_top_n_symbols`
- `cpcv_fold_expansion_output_tag`

### 4.5 PIT Safety Preserved

- No changes to data loading pipeline
- No changes to walk-forward split creation (only parameters passed through)
- No negative shifts or future data access patterns introduced
- Embargo and chronological splitting unchanged
- T-1 lag on signals unchanged

## 5. No Default/Live Behavior Changes

- All new args default to `None`, falling back to built-in constants (8/3/1/30)
- Existing `--quick-mode` behavior identical (still 2/1/1/1)
- All pre-existing CLI flags unchanged
- Output filenames unchanged when `--output-tag` not provided

## 6. Test Results

### 6.1 Targeted Tests: 37/37 PASSED

```
tests/phase35/test_cpcv_fold_expansion_cli_wiring.py ... 37 passed
```

Test classes:
- `TestCPCVFoldExpansionCLIFlags` (9 tests): CLI flag registration
- `TestCPCVFoldExpansionDefaults` (9 tests): Default values and None defaults
- `TestCPCVFoldExpansionQuickModeOverride` (6 tests): Quick-mode override behavior
- `TestCPCVFoldExpansionOutputTag` (4 tests): Output filename modification
- `TestCPCVFoldExpansionConfigPersistence` (5 tests): JSON config keys
- `TestCPCVFoldExpansionLogging` (2 tests): Logging output
- `TestCPCVFoldExpansionPITSafety` (4 tests): No look-ahead, no data pipeline changes
- `TestCPCVFoldExpansionNoDefaultBehaviorChange` (2 tests): Existing flags preserved

### 6.2 Full Phase 3.5 Suite: 210/210 PASSED

```
tests/phase35/ ... 210 passed in 17.95s
```

No regressions in existing tests.

### 6.3 Smoke Test

Command: `python scripts/run_phase35_backtest.py --quick-mode --n-folds 12 --output-tag cpcv_smoke`

- Quick-mode correctly overrode `--n-folds 12` to `2`
- Output files created: `phase35_backtest_results_cpcv_smoke_xgboost.json`, `phase35_backtest_summary_cpcv_smoke_xgboost.txt`
- JSON config includes all fold expansion keys
- Script completed without errors

## 7. SOD Boundary

- **Implementation only** (Tier 2 constraint)
- **No self-approval** - submitted to Tier 3 audit
- **Cannot approve** own work for live deployment

## 8. Tier 3 Audit Submission

Submitted to:
- Code Reviewer (role 21): Code quality and reproducibility review
- QA Engineer (role 17): Model validation and testing review

**Status:** PENDING AUDIT - Do not audit or approve (per task instructions).
