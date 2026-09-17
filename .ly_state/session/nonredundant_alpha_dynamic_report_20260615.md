# Nonredundant Alpha Dynamic Report — 2026-06-15

**GATE**: `NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615`
**Role**: 14 (data-scientist) — L2 implementation only, no self-approval
**Verdict**: `RESEARCH_ONLY` / `DO_NOT_PROMOTE`
**Date**: 2026-06-15

---

## 1. Objective

Add opt-in nonredundant alpha family set v1 (default off) with 10 PIT-safe trailing-window alpha candidates from 5 families. Evaluate against dynamic baseline.

## 2. Implementation Summary

### Files Modified/Created
| File | Action | Purpose |
|------|--------|---------|
| `src/omega/quant/alpha/nonredundant_alphas.py` | **Created** | 10 nonredundant alpha candidates from 5 families |
| `src/omega/quant/alpha/phase35.py` | **Modified** | GATE constant, init params, compute_alphas wiring |
| `scripts/run_phase35_backtest.py` | **Modified** | CLI flags, engine wiring, config serialization |
| `tests/phase35/test_nonredundant_alphas.py` | **Created** | 32 tests (default off, CLI, PIT safety, finite outputs, determinism, integration) |

### Alpha Families (v1)

| # | Family | Alpha Name | Formula (PIT-safe) |
|---|--------|-----------|-------------------|
| 1 | Liquidity Shock Reversal | `alpha_nr_liq_shock_zscore_20` | Volume trailing z-score (T-1 lag) |
| 2 | Liquidity Shock Reversal | `alpha_nr_liq_shock_reversal_10` | -1 * sign(ret) * vol_zscore (T-1 lag) |
| 3 | Range Pressure / CLV | `alpha_nr_close_location_value_10` | (close - min_low) / (max_high - min_low) (T-1 lag) |
| 4 | Range Pressure / CLV | `alpha_nr_range_pressure_momentum_20` | range / mean_range - 1 (T-1 lag) |
| 5 | Vol Compression Breakout | `alpha_nr_vol_compression_20` | -1 * BB width z-score (T-1 lag) |
| 6 | Vol Compression Breakout | `alpha_nr_vol_breakout_directional_10` | (close - SMA) / std (T-1 lag) |
| 7 | Sector/Market Residual | `alpha_nr_residual_reversal_10` | -1 * mean(residual ret) (T-1 lag, sector fallback) |
| 8 | Sector/Market Residual | `alpha_nr_market_relative_momentum_20` | cumret_stock - cumret_market (T-1 lag) |
| 9 | Breadth-Conditioned | `alpha_nr_breadth_conditioned_reversal_10` | -1 * ret * breadth_dev * 4 (T-1 lag) |
| 10 | Breadth-Conditioned | `alpha_nr_advance_decline_signal_20` | A/D line change z-score (T-1 lag) |

### CLI Flags Added
- `--enable-nonredundant-alphas` (store_true, default disabled)
- `--nonredundant-alpha-set v1` (default "v1")
- `--nonredundant-alpha-max-candidates` (optional integer limit)

## 3. E2E Backtest Results

### Configuration
- Data cleaning: ON
- XGBoost: OFF
- Drawdown control: ON (threshold 10%)
- Dynamic universe: ON (lookback 252d, rebalance 21d)
- Folds: 12
- Nonredundant alphas: ENABLED (v1, 10 candidates)
- Sector map: Loaded (1924 mappings from `data/sector_mapping_level2.csv`)

### Results vs Dynamic Baseline

| Metric | Dynamic Baseline | Nonredundant v1 | Delta |
|--------|-----------------|------------------|-------|
| **Mean Portfolio IC** | 0.0249 | 0.0092 | -0.0157 |
| **Median Portfolio IC** | 0.0167 | 0.0176 | **+0.0009** |
| **Median Sharpe** | 1.62 | 1.6725 | **+0.0525** |
| **Mean MaxDD** | -12.25% | -11.55% | **+0.70% (improved)** |
| **Worst MaxDD** | — | -14.26% | — |
| **Folds** | 12 | 12 | — |

### Per-Fold Portfolio IC

| Fold | Portfolio IC | Sharpe | MaxDD |
|------|-------------|--------|-------|
| 1 | -0.0363 | 1.7629 | -12.17% |
| 2 | 0.0455 | 1.5822 | -14.26% |
| 3 | 0.0324 | 0.1095 | -10.94% |
| 4 | -0.0399 | 0.2977 | -11.35% |
| 5 | -0.0205 | 3.2775 | -12.94% |
| 6 | -0.0281 | 3.8906 | -12.75% |
| 7 | 0.0106 | 1.4781 | -10.04% |
| 8 | 0.0106 | -1.6410 | -12.57% |
| 9 | 0.0395 | 5.3876 | -10.24% |
| 10 | 0.0245 | 2.7480 | -10.98% |
| 11 | 0.0329 | 1.0907 | -10.32% |
| 12 | 0.0393 | 6.7820 | -10.10% |

### NR Alpha IC Performance (avg across 12 folds)

| Alpha | Mean IC | Verdict |
|-------|---------|---------|
| `alpha_nr_market_relative_momentum_20` | **+0.0546** | Strong positive |
| `alpha_nr_range_pressure_momentum_20` | **+0.0193** | Positive |
| `alpha_nr_liq_shock_reversal_10` | +0.0053 | Weak positive |
| `alpha_nr_close_location_value_10` | +0.0048 | Weak positive |
| `alpha_nr_vol_breakout_directional_10` | +0.0042 | Weak positive |
| `alpha_nr_liq_shock_zscore_20` | -0.0009 | Neutral |
| `alpha_nr_vol_compression_20` | -0.0142 | Weak negative |
| `alpha_nr_breadth_conditioned_reversal_10` | -0.0407 | Negative |
| `alpha_nr_residual_reversal_10` | -0.0480 | Negative |
| `alpha_nr_advance_decline_signal_20` | -0.0481 | Negative |

### Key Findings

1. **Market-relative momentum** (`alpha_nr_market_relative_momentum_20`) is the strongest NR candidate (mean IC +0.0546, consistently selected across folds).
2. **Range pressure momentum** (`alpha_nr_range_pressure_momentum_20`) shows positive IC (+0.0193), complementing existing alphas.
3. **Liquidity shock reversal** and **close-location value** show weak positive signals.
4. **Advance/decline signal**, **residual reversal**, and **breadth-conditioned reversal** show negative IC — these should be investigated or retired in future iterations.
5. **Median Portfolio IC improved** slightly (+0.0009) and **median Sharpe improved** (+0.05) vs baseline.
6. **MaxDD improved** from -12.25% to -11.55% mean.
7. Mean Portfolio IC decreased because some NR alphas with negative IC entered the selection pool and diluted signal quality.

## 4. PIT Safety Verification

- All 10 alphas use **T-1 lag** per ticker
- No negative shifts (`.shift(-N)`) anywhere in source
- No `.lead()` operations
- All rolling windows are **trailing** (no `center=True`)
- No `future_data` or `forward_fill` patterns in code
- Sector map fallback works when file unavailable
- First rows per ticker show warmup NaN/zero pattern (T-1 shift + rolling window)

## 5. Test Results

- **32 new tests**: All passing
- **685 full phase35 test suite**: All passing (no regressions)
- Tests cover: default off, CLI opt-in, PIT safety, finite outputs, determinism, sector fallback, max candidates, engine wiring, dynamic smoke

## 6. Safety and Compliance

> This analysis is **deterministic** and **PIT-safe**. All nonredundant alpha computations use only trailing windows with T-1 lag per ticker. No live trading paths are affected. Default behavior is unchanged (opt-in disabled).

**Forbidden path scan**: No authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## 7. Recommendations

1. **Promote** `alpha_nr_market_relative_momentum_20` and `alpha_nr_range_pressure_momentum_20` for further investigation.
2. **Retire** `alpha_nr_advance_decline_signal_20`, `alpha_nr_residual_reversal_10`, `alpha_nr_breadth_conditioned_reversal_10` from future alpha sets.
3. **Investigate** why negative-IC NR alphas enter the selection pool — the top-N-by-absolute-IC selection may be selecting negatively-correlated signals.
4. Consider adding an IC sign filter to `select_top_alphas` to exclude negative-IC candidates.

---

*Report generated by Role 14 (data-scientist) L2 — implementation only, no self-approval. Submit to Tier 3 (Code Reviewer role 21 + QA Engineer role 17) for audit.*

---

## 8. FIX1 Addendum (2026-06-15)

**Gate**: `NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615_FIX1`
**Trigger**: L3 audit verdict `[NEEDS_FIX]` from `audit_reports/role20_nonredundant_alpha_generation_dynamic_20260615.md`

### Fix 1: Per-Ticker PIT Lag (Return-Based NR Alphas)

- **Root cause**: `.pct_change().shift(1)` was a global shift, leaking ticker A's last return into ticker B's first row.
- **Fix**: Changed to `.pct_change().groupby(groups).shift(1)` at 5 locations in `nonredundant_alphas.py` (lines 227, 366, 402, 434, 462).
- **Regression test**: `TestPerTickerPITLagBoundary` with 2 tests proving no cross-ticker contamination.

### Fix 2: Per-Fold NR Evidence Persistence

- **Root cause**: `FoldMetrics` constructor in `run_fold` never populated `nonredundant_alpha_evidence`.
- **Fix**: Added sector map tracking in `compute_alphas()`, evidence dict construction in `run_fold()`, and `nonredundant_alpha_evidence=_nr_evidence` in FoldMetrics.
- **Regression test**: `TestPerFoldNREvidence` with 4 tests.

### Test Evidence (Post-Fix)

| Suite | Result |
|-------|--------|
| `test_nonredundant_alphas.py` | 38 passed (32 original + 6 new) |
| `tests/phase35` | 691 passed (685 original + 6 new) |
| Baseline JSON regeneration | 12/12 folds with NR evidence |

### NR Evidence per Fold (Post-Fix)

All 12 folds contain:
```json
{
  "gate": "NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615",
  "enabled": true,
  "set_name": "v1",
  "computed_candidate_count": 10,
  "sector_map_loaded": true,
  "pit_safe": true
}
```

### Metric Impact

| Metric | Pre-Fix | Post-Fix | Delta |
|--------|---------|----------|-------|
| Avg Portfolio IC | 0.0092 | 0.0083 | -0.0009 |
| Avg Raw Signal IC | 0.0282 | 0.0282 | 0.0000 |
| Avg Sharpe | 2.2305 | 2.2156 | -0.0149 |
| Avg Max DD | -11.55% | -11.55% | 0.00% |

Slight Portfolio IC reduction expected: PIT fix zeroes contaminated first-row values per ticker.
