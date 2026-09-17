# L2 Session Report: CPCV Fold Transaction Cost Leakage Fix

**Role**: role_id=14, data-scientist (OpenCode L2)  
**Task**: Fix CPCV fold transaction cost leakage where non-contiguous test dates cause cost overcharge on purge/embargo gaps  
**Gate**: CPCV_TCOST_LEAKAGE_FIX_20260625  
**Session**: l2_role14_cpcv_tcost_leakage_fix_20260625  
**Date**: 2026-06-25

## Repo-Local Skill Sources Read

| Source | Path |
|--------|------|
| Role spec | `.agents/agent/data-scientist.md` |
| python-patterns skill | `.agents/skills/python-patterns/SKILL.md` |
| clean-code skill | `.agents/skills/clean-code/SKILL.md` |
| backtesting-pit-safety skill | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| quant-research skill | `.agents/skills/quant-research/SKILL.md` |

**Forbidden Path Scan**: No reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`.

## Root Cause

CPCV folds have non-contiguous test dates (scattered blocks across the dataset). When `run_single_fold()` in `backtest_hybrid_regime.py` calls `pipeline.execute()` with the full `[min_test_date, max_test_date]` date range, `apply_realistic_tc` in `execution_sim.py` charges transaction costs on **every** bar transition — including gaps between non-adjacent test blocks (purge/embargo periods). These spurious costs leak into fold metrics, understating strategy returns.

## Changes

### 1. `src/omega/quant/portfolio/execution_sim.py`

- Added `active_dates_mask: np.ndarray | None = None` parameter to `apply_realistic_tc`.
- When mask is not None, non-active bars pass gross returns unchanged (`net_rets[i] = gross_rets[i]`) with zero cost contribution — preserving the sequential weight delta chain for correct prev_w tracking.
- Added per-bar cost tracking arrays (`cost_per_bar`, `slippage_per_bar`, `fee_per_bar`) for accurate active-date-only breakdown statistics.
- Breakdown `avg_cost_per_bar_bps` and `total_cost` computed from active-date-only bars.
- Backward compatible: `active_dates_mask=None` behaves identically to pre-fix.

### 2. `src/omega/quant/pipeline_v2.py`

- Added `active_dates: pd.DatetimeIndex | None = None` parameter to `TradingPipelineV2.execute()`.
- Constructs mask via `common_idx.isin(active_dates)` and passes to `apply_realistic_tc`.
- Filters `net_rets` and `weights` to active dates after TC call (non-active dates excluded from all downstream metrics).
- Backward compatible: `active_dates=None` skips all filtering.

### 3. `scripts/backtest_hybrid_regime.py`

- Passes `active_dates=pd.DatetimeIndex(test_dates)` to `pipeline.execute()` in `run_single_fold()`.

## Verification

- Syntax checked: all 3 files pass `ast.parse()`.
- Unit tests in `quant_test_execution_sim.py`: all previously passing tests still pass.
- Pre-existing failure `test_slippage_scales_with_capital` unchanged (nonlinear slippage model compresses impact at high capital; unrelated to changes).

## Caller Audit

| Caller | Uses CPCV? | Needs active_dates? | Status |
|--------|-----------|-------------------|--------|
| `backtest_hybrid_regime.py` | Yes | Yes | Fixed |
| `backtest_advanced_features.py` | No (contiguous range) | No | OK |
| `tune_quant_performance.py` | No (contiguous range) | No | OK |
| `backtest_v2_cpcv.py` (legacy) | Yes, but pre-filters test data at caller | No | OK |

## Design Decisions

1. **Mask approach over pre-filtering weights**: Using `active_dates_mask` in `apply_realistic_tc` preserves the sequential `prev_w` delta chain across non-active bars. Pre-filtering weights would break `prev_w = w[i-1]` across gaps, causing incorrect turnover calculation on active bars.
2. **Per-bar cost arrays**: Added for accurate active-date-only breakdown statistics. Previously, `avg_cost_per_bar_bps` averaged over all bars including non-test gaps. Now uses only active bars.
3. **Backward compatibility**: `active_dates=None` (default) in all changed functions preserves existing behavior for non-CPCV callers.
