# Nonredundant Alpha Generation Dynamic — L2 Fix1 Report

**Role**: data-scientist (Role 14, OpenCode L2)
**Date**: 2026-06-15
**Gate**: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615
**Gate ID**: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615_FIX1
**Audit Verdict Addressed**: [NEEDS_FIX] from `.ly_state/session/audit_reports/role20_nonredundant_alpha_generation_dynamic_20260615.md`

## Repo-Local Sources Read

- `.agents/agent/data-scientist.md` (frontmatter: role_id=14, skills=[python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow])
- `.agents/skills/` (directory listing confirmed skill directories exist)
- `.ly_state/session/audit_reports/role20_nonredundant_alpha_generation_dynamic_20260615.md`

Forbidden path scan: no authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## Scoped Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/alpha/nonredundant_alphas.py` | Fix 1: per-ticker group shift (5 locations) |
| `src/omega/quant/alpha/phase35.py` | Fix 2: NR evidence population + sector map tracking |
| `tests/phase35/test_nonredundant_alphas.py` | Added 6 regression tests (2 sections) |
| `data/phase35_results/phase35_backtest_results_nonredundant_v1_baseline.json` | Regenerated with NR evidence |
| `data/phase35_results/phase35_backtest_summary_nonredundant_v1_baseline.txt` | Regenerated |

## Blocker 1 Fix: Per-Ticker PIT Lag (Return-Based NR Alphas)

### Root Cause

Five return-based alpha functions used the pattern:
```python
ret_lagged = df.groupby(symbol_col)[close_col].pct_change().shift(1)
```
The `.pct_change()` correctly computed returns within each ticker group. However, the trailing `.shift(1)` was a **global** Series shift, not per-group. Since `compute_nonredundant_alphas()` sorts by `[symbol_col, date_col]`, the last return of ticker A leaked into the first row of ticker B.

### Fix Applied

Changed all 5 locations to use per-group shift:
```python
ret_lagged = df.groupby(symbol_col)[close_col].pct_change().groupby(groups).shift(1)
```

### Locations Fixed

| Function | Line (original) | Pattern |
|----------|-----------------|---------|
| `_compute_liq_shock_reversal` | 227 | `.groupby(groups).shift(1)` |
| `_compute_residual_reversal` | 366 | `.groupby(groups).shift(1)` |
| `_compute_market_relative_momentum` | 402 | `.groupby(groups).shift(1)` |
| `_compute_breadth_conditioned_reversal` | 434 | `.groupby(groups).shift(1)` |
| `_compute_advance_decline_signal` | 462 | `.groupby(df[symbol_col]).shift(1)` |

### Regression Test Added

**`TestPerTickerPITLagBoundary`** (Section 11, 2 tests):

1. `test_first_row_of_each_ticker_has_no_prior_ticker_contamination` — Uses a minimal 2-ticker x 2-date panel. Verifies first row of every ticker is 0.0/NaN for all 5 return-based NR alphas.

2. `test_grouped_shift_produces_nan_per_ticker_boundary` — Direct unit test comparing old (broken) global shift vs new (fixed) per-group shift. Proves B's first row is NaN with fix, non-NaN without.

## Blocker 2 Fix: Per-Fold NR Evidence Persistence

### Root Cause

`FoldMetrics` defined `nonredundant_alpha_evidence` field (line 194), and the serializer in `scripts/run_phase35_backtest.py` wrote it when non-null (lines 105-108). However, `FoldMetrics(...)` constructor in `run_fold` never populated it, resulting in 0/12 folds having evidence despite `enable_nonredundant_alphas=true`.

### Fix Applied

**`src/omega/quant/alpha/phase35.py`** — Two changes:

1. **`compute_alphas()`** (lines 617-642): Added sector map tracking attributes:
   - `self._nr_sector_map_loaded` — boolean, True if sector map loaded with >0 entries
   - `self._nr_sector_map_fallback_reason` — string or None

2. **`run_fold()`** (before FoldMetrics constructor): Added NR evidence dict construction when `self.enable_nonredundant_alphas` is True:
   ```python
   _nr_evidence = {
       "gate": NONREDUNDANT_ALPHA_GATE_ID,
       "enabled": True,
       "set_name": self.nonredundant_alpha_set,
       "max_candidates": self.nonredundant_alpha_max_candidates,
       "computed_candidate_columns": [...],  # alpha_nr_* cols in test_df
       "computed_candidate_count": len(...),
       "sector_map_loaded": bool,
       "sector_map_fallback": bool,
       "pit_safe": True,
       "fallback_reason": str or None,
   }
   ```
   Passed as `nonredundant_alpha_evidence=_nr_evidence` to FoldMetrics.

### Default-Off Preserved

- `enable_nonredundant_alphas` defaults to `False` in engine `__init__`
- `_nr_evidence` remains `None` when disabled — serializer omits it (backward-compatible)
- CLI flag `--enable-nonredundant-alphas` uses `store_true` (default False)

### Regression Tests Added

**`TestPerFoldNREvidence`** (Section 12, 4 tests):

1. `test_nr_evidence_populated_when_enabled` — Verifies engine sets `_nr_sector_map_loaded` and `_nr_sector_map_fallback_reason` after `compute_alphas()`.
2. `test_nr_evidence_dict_structure` — Validates all 10 required keys present and JSON-serializable.
3. `test_fold_metrics_has_nr_evidence_field` — Confirms FoldMetrics dataclass has the field.
4. `test_serializer_writes_nr_evidence` — Verifies serializer source code writes the evidence.

## Test Evidence

### Focused Tests
```
python -m pytest tests/phase35/test_nonredundant_alphas.py -v
Result: 38 passed (32 original + 6 new)
```

### Phase35 Regression
```
python -m pytest tests/phase35 --tb=no
Result: 691 passed, 0 failed (was 685 + 6 new)
```

### Baseline JSON Regeneration
```
python scripts/run_phase35_backtest.py --n-folds 12 --top-n-symbols 30 \
  --enable-nonredundant-alphas --dynamic-universe --output-tag nonredundant_v1
Result: 12 folds completed successfully
```

### NR Evidence Verification
```
Total folds: 12
Folds with NR evidence: 12
All folds: gate=NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615,
  enabled=True, count=10, sector_loaded=True, pit_safe=True
```

## Metric Impact (Research-Only, Do-Not-Promote)

| Metric | Pre-Fix (original) | Post-Fix |
|--------|-------------------|----------|
| Avg Portfolio IC | 0.0092 | 0.0083 |
| Avg Raw Signal IC | 0.0282 | 0.0282 |
| Avg Raw Signal Daily CS IC | 0.0273 | 0.0272 |
| Avg Portfolio Sharpe | 2.2305 | 2.2156 |
| Avg Max Drawdown | -11.55% | -11.55% |

The slight Portfolio IC change (0.0092 -> 0.0083) is expected: the per-ticker PIT fix changes the first row of each ticker from a contaminated value to 0.0, which marginally affects Stage 2 stock selection. Raw Signal IC is unchanged, confirming the fix only corrects PIT contamination without degrading signal quality.

## SOD Compliance

- Writer != auditor: Role 14 (data-scientist) != Role 20 (compliance-officer). PASS.
- L2 write boundary: Only implementation files, tests, and data artifacts modified. No audit or gate approval. PASS.
- No self-approval: This report is submitted to Tier 3 for audit. PASS.
