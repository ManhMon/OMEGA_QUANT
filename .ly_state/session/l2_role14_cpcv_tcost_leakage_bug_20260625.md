# L2 Implementation Report ? CPCV Transaction Cost Leakage Bug Fix

## 1. Role Specification & Skills Loaded

- **Role ID**: 14 (data-scientist)
- **Role Spec File**: .agents/agent/data-scientist.md
- **Loaded Skills**: 
  - .agents/skills/python-patterns/SKILL.md
  - .agents/skills/clean-code/SKILL.md
  - .agents/skills/testing-patterns/SKILL.md
  - .agents/skills/systematic-debugging/SKILL.md
  - .agents/skills/performance-profiling/SKILL.md
  - .agents/skills/quant-research/SKILL.md
  - .agents/skills/vietnam-market-data/SKILL.md
  - .agents/skills/backtesting-pit-safety/SKILL.md
  - .agents/skills/data-science-workflow/SKILL.md
- **Forbidden Path Scan Result**: Pass. No authoritative reliance on global or scratch ag-kit paths. All skills loaded strictly from REPO_SKILL_ROOT.

## 2. Problem Diagnosis

When running walk-forward CPCV backtests via scripts/backtest_hybrid_regime.py, a ValueError or AttributeError was triggered in src/omega/quant/pipeline_v2.py at line 901:
`python
AttributeError: 'numpy.ndarray' object has no attribute 'to_numpy'
`
This is because common_idx was a 
umpy.ndarray (returned by intersecting column names or indexes in some execution contexts, or index intersection logic in pandas/numpy environment). A 
umpy.ndarray does not have a .to_numpy() method (it is already a numpy array).

## 3. Implementation Details

We surgically modified src/omega/quant/pipeline_v2.py to convert common_idx to pd.Index before calling .isin(), and check if the returned boolean mask has a .to_numpy() method to convert it safely to a raw numpy array.

`python
        active_dates_mask = None
        if active_dates is not None:
            active_dates_mask = pd.Index(common_idx).isin(active_dates)
            if hasattr(active_dates_mask, "to_numpy"):
                active_dates_mask = active_dates_mask.to_numpy()
`

This ensures compatibility whether common_idx is a pd.Index or a 
umpy.ndarray, resolving the crash.

## 4. Verification

The fix was verified by successfully running a smoke-test backtest with the following parameters:
- Command: python scripts/backtest_hybrid_regime.py --folds 3 --n-test-folds 1 --start-date 2024-01-01 --end-date 2026-06-01
- Outcome: Backtest completed all 3 folds successfully without any crashes, saving the comparison output to data/phase35_results/hybrid_regime_cpcv_comparison.json.
