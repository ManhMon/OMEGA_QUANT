# L2 Implementation Report: DYNAMIC_REBALANCE_UNIVERSE_20260615

**Role**: 14 — Data Scientist (L2 Implementation)
**Gate**: DYNAMIC_REBALANCE_UNIVERSE_20260615
**Date**: 2026-06-15
**Status**: IMPLEMENTED — awaiting Tier 3 audit

---

## 1. Objective

Implement opt-in per-rebalance dynamic universe selection for the Phase 3.5
walk-forward backtest. For each rebalance date R, select top-N symbols using
ONLY trailing history from `[R - lookback_days, R)` — strictly no data from R
or later. Filters: ADTV >= 5B VND, avg close >= 5000 VND, min history days.

## 2. Files Changed

| File | Change |
|------|--------|
| `scripts/phase35_data_loader.py` | Added `DynamicUniverseSelector` class + `DYNAMIC_UNIVERSE_GATE_ID` constant |
| `src/omega/quant/alpha/phase35.py` | Added `dynamic_universe_schedule` param to engine `__init__`; filter eligible symbols in `_apply_stage2_constraints` at rebalance; added `dynamic_universe_evidence` field to `FoldMetrics` |
| `scripts/run_phase35_backtest.py` | Added `--dynamic-universe`, `--dynamic-universe-lookback-days`, `--dynamic-universe-rebalance-days`, `--dynamic-universe-top-n` CLI args; build schedule before engine; persist evidence in results JSON; added `serialize_fold_details` wiring |
| `tests/phase35/test_phase35_dynamic_universe.py` | **New file**: 34 tests covering PIT safety, filters, JSON serialization, determinism, CLI flags, source verification |

## 3. Implementation Summary

### 3.1 `DynamicUniverseSelector` (phase35_data_loader.py)

- **Class**: `DynamicUniverseSelector`
- **Constructor params**: `lookback_days=252`, `rebalance_days=21`, `top_n=30`, `min_history_days=60`
- **Methods**:
  - `compute_rebalance_dates(dates)`: Every `rebalance_days`-th trading date
  - `select_for_rebalance(full_df, rebalance_date)`: PIT-safe single-date selection
  - `build_dynamic_universe_schedule(full_df)`: Full schedule + per-rebalance evidence
  - `get_evidence()`: Return stored evidence list
- **Filters**: ADTV >= 5B VND, avg close >= 5000 VND, min history days
- **Ranking**: Mean daily value (close * volume) descending, top N
- **Turnover**: Jaccard distance between consecutive rebalance symbol sets

### 3.2 Engine Wiring (phase35.py)

- `Phase35WalkForwardEngine.__init__` accepts `dynamic_universe_schedule: Optional[Dict[str, List[str]]]`
- `_apply_stage2_constraints`: At each rebalance checkpoint, if schedule has entry for the date, restricts `alpha_row` to eligible symbols from the schedule
- Carry-forward: If no entry for exact date, uses last known eligible set
- `FoldMetrics.dynamic_universe_evidence` field added for per-fold persistence

### 3.3 CLI Integration (run_phase35_backtest.py)

| Flag | Default | Description |
|------|---------|-------------|
| `--dynamic-universe` | False (disabled) | Enable PIT per-rebalance dynamic universe |
| `--dynamic-universe-lookback-days` | 252 | Trailing lookback window (calendar days) |
| `--dynamic-universe-rebalance-days` | 21 | Rebalance cadence (calendar days) |
| `--dynamic-universe-top-n` | None (falls back to `--top-n-symbols`) | Top N per rebalance |

### 3.4 Evidence Persisted

Per-rebalance JSON-serializable evidence dict:

```json
{
  "gate": "DYNAMIC_REBALANCE_UNIVERSE_20260615",
  "rebalance_date": "2021-02-01",
  "selection_window_start": "2020-05-25",
  "selection_window_end_exclusive": "2021-02-01",
  "selection_end": "2021-01-29",
  "selection_end_before_rebalance": true,
  "selected_symbols": ["ACB", "CTG", "FPT", ...],
  "n_selected": 30,
  "n_candidates_before_filter": 120,
  "n_candidates_after_filter": 85,
  "top_n_requested": 30,
  "lookback_days": 252,
  "min_adtv_vnd": 5000000000.0,
  "min_avg_close_vnd": 5000.0,
  "min_history_days": 60,
  "turnover_from_previous": 0.12,
  "symbols_added": ["HPG"],
  "symbols_removed": ["MSN"],
  "pit_safe": true
}
```

## 4. Test Results

### 4.1 Focused Tests (test_phase35_dynamic_universe.py)

```
34 passed, 0 failed (7.56s)
```

Test classes:
- `TestDynamicUniverseDefaultDisabled` (6 tests): CLI defaults correct
- `TestPITSafetyNoFutureLeakage` (3 tests): selection_end < rebalance_date always
- `TestMembershipChanges` (3 tests): Turnover computed, membership changes tracked
- `TestEvidenceSerializable` (5 tests): All evidence JSON-serializable, required keys present
- `TestFilters` (4 tests): ADTV/price/history filters work, empty df handled
- `TestDeterministicSelection` (2 tests): Same input → same output
- `TestConstructorValidation` (3 tests): Invalid params raise ValueError
- `TestStaticScriptChecks` (8 tests): Source files contain expected flags and classes

### 4.2 Regression Tests (all phase35 tests)

```
607 passed, 0 failed (24.11s)
```

No regressions in any existing test file:
- test_phase35_rolling_universe.py: 18 passed
- test_p9_dynamic_rebalance_pit_safety.py: 4 passed
- test_stage2_wiring.py: 21 passed
- test_stage3_ml_gate_integration.py: 25 passed
- test_p10_multi_horizon_blend.py: 43 passed
- test_p11_data_cleaning.py: 35 passed
- test_regime_routing.py: 41 passed
- All others: passed

## 5. PIT Safety Verification

| Check | Result |
|-------|--------|
| Selection window `[R - lookback, R)` exclusive | Verified by assertion in `select_for_rebalance` |
| `selection_end < rebalance_date` always | Tested in `TestPITSafetyNoFutureLeakage` |
| `selection_end_before_rebalance = True` in all evidence | Tested |
| No test data in selection | Selection uses `full_df` filtered to `< R` only |
| Schedule pre-built before engine runs | Built in `main()` before `Phase35WalkForwardEngine` constructor |

## 6. Design Decisions

1. **Pre-built schedule vs per-fold**: Schedule is built once on full data before walk-forward, then engine looks up by date string. This avoids per-fold recomputation and keeps selection PIT-safe (only uses data before each rebalance date).

2. **Carry-forward for missing dates**: If the schedule has no entry for an exact rebalance date (e.g., due to calendar mismatch), the last known universe is carried forward. This prevents silent universe expansion.

3. **Turnover metric**: Jaccard distance between consecutive rebalance sets, providing a [0, 1] turnover proxy consistent with quant-research skill principles.

4. **Opt-in default**: Default disabled (`--dynamic-universe` not set) preserves backward compatibility. Static universe behavior is unchanged.

## 7. Repo-Local Source Files Read

| Path | Purpose |
|------|---------|
| `.agents/agent/data-scientist.md` | Role definition (role 14, tier 2) |
| `.agents/skills/python-patterns/SKILL.md` | Python patterns |
| `.agents/skills/clean-code/SKILL.md` | Clean code standards |
| `.agents/skills/testing-patterns/SKILL.md` | Testing patterns |
| `.agents/skills/systematic-debugging/SKILL.md` | Debugging methodology |
| `.agents/skills/performance-profiling/SKILL.md` | Performance profiling |
| `.agents/skills/quant-research/SKILL.md` | Quant research principles |
| `.agents/skills/vietnam-market-data/SKILL.md` | Vietnam market data |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | Backtesting PIT safety |
| `.agents/skills/data-science-workflow/SKILL.md` | Data science workflow |

## 8. Forbidden Path Scan Result

No authoritative reliance on forbidden paths:
- `.gemini\antigravity-ide\scratch\ag-kit` — non-authoritative, not used as source
- `.openclaw\skills` — non-authoritative, not used as source
- `C:\Users\GHC\.agents` — non-authoritative, not used as source
- `.codex\memories` — non-authoritative, not used as source

## 9. Metrics

| Metric | Value |
|--------|-------|
| Files changed | 4 |
| New test file | 1 |
| Tests added | 34 |
| Total phase35 tests passing | 607/607 |
| Lines added (approx) | ~450 |
| PIT violations | 0 |
| JSON serialization failures | 0 |

---

**Tier 3 Audit Submission**: This implementation is submitted to Code Reviewer (role 21) and QA Engineer (role 17) for audit. Cannot proceed until both return [APPROVED].
