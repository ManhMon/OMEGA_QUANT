# ALPHA_PRIMITIVES Audit

Verdict: **[NEEDS_FIX]**

Scope audited:
- `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_primitives.py`
- `OMEGA_QUANT/tests/phase3/test_alpha_primitives.py`

## Test Execution
Command:
```bash
python -m pytest OMEGA_QUANT/tests/phase3/test_alpha_primitives.py -v
```
Result: **10 passed**.

## Findings

### 1) Math accuracy (IC, Sharpe, MDD)
- `calculate_ic`: Uses `scipy.stats.pearsonr` correctly for normal cases.
- `calculate_rank_ic`: Uses `scipy.stats.spearmanr` correctly.
- `calculate_sharpe`: Formula is standard annualized Sharpe.
- `calculate_max_drawdown`: Standard cumprod/cummax drawdown logic, but baseline handling can miss first-period drawdown from initial capital (1.0) when first return is negative.

### 2) Vectorization
- No row loops (`iterrows` etc.).
- Implementation is vectorized via pandas/numpy ops.

### 3) Edge cases (NaN, division by zero)
- NaN filtering handled in IC/rank IC/sharpe/MDD.
- Turnover handles index mismatch + NaN via aligned DataFrame + `.fillna(0)`.
- Sharpe handles zero/NaN std by returning `np.nan`.

**Critical issue:**
- `calculate_ic` crashes when valid sample count < 2.
- Repro:
  ```python
  calculate_ic(pd.Series([1.0]), pd.Series([2.0]))
  ```
  raises `ValueError` from `pearsonr`.
- Expected behavior for primitive metric fn: return `np.nan` for insufficient sample, not raise.

**Additional robustness gap:**
- `calculate_max_drawdown` can produce incorrect first-point drawdown baseline when first return < 0 because initial capital anchor (1.0) not included in peak path.

### 4) PIT safety (lookahead bias)
- No explicit time-shift or forward fill done inside primitives.
- Functions operate pointwise on provided series only.
- No lookahead logic detected in math primitives.

## Required fixes
1. In `calculate_ic` and `calculate_rank_ic`, guard `valid.sum() < 2` and return `np.nan`.
2. In `calculate_max_drawdown`, include initial capital baseline (1.0) before cumulative path for mathematically consistent MDD from start.
3. Add tests:
   - IC with 0/1 valid pair returns `np.nan` (no exception)
   - Rank IC with 0/1 valid pair returns `np.nan`
   - MDD first negative return reflects drawdown from initial capital

## Final
Current implementation passes existing tests but has edge-case correctness bug in IC and robustness gap in MDD baseline.

**Verdict: [NEEDS_FIX]**
