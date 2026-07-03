# Automated Alpha OOS Winner Guard Allowlist Report
## GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
### Date: 2026-06-15

---

## 1. Objective

Complete the opt-in research-only allowlist so `auto_top5_real_ic_20260615` alphas
pass the formulaic winner guard only when an explicit flag is enabled.
Default behavior is unchanged (auto alphas remain blocked).

## 2. Problem Statement

The existing baseline run (`phase35_backtest_results_automated_oos_bundle_20260615_baseline.json`)
had:
- `enable_automated_oos_bundle: true` — auto bundle signals injected
- `formulaic_winner_guard: true` — winner guard constraining selection

But the auto bundle alphas (auto_rsi_14, auto_mr_zscore_20, auto_mom_ret_60,
auto_mom_ret_20, auto_vol_std_ratio_10_30) were **excluded** from the winner
guard allowlist.  In every fold, the winner guard blocked all auto alphas
from selection, even when they had the highest train IC.

Example: Fold 6 had auto_rsi_14 IC=0.20, auto_mr_zscore_20 IC=0.14,
auto_mom_ret_60 IC=0.20, auto_mom_ret_20 IC=0.19 — all blocked by guard.

## 3. Implementation

### 3.1 Changes to `src/omega/quant/alpha/phase35.py`

- **Gate constant**: `AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_GATE_ID`
  (already existed from prior task — confirmed present)
- **Constructor parameter**: `enable_auto_winner_guard_allowlist: bool = False`
  with validation (`must be bool`)
- **`apply_formulaic_winner_guard()`**: Builds effective allowlist =
  base allowlist + auto bundle names (when flag AND OOS bundle both True).
  Uses `_effective_allowlist` for both primary filter and fallback path.
- **`filter_fallback_by_winner_guard()`**: Same effective allowlist logic.
- **Evidence dict**: Extended with `auto_winner_guard_allowlist_enabled`,
  `auto_winner_guard_allowlist_names`, `base_allowlist`.

### 3.2 Changes to `scripts/run_phase35_backtest.py`

- **CLI flag**: `--enable-auto-winner-guard-allowlist` (action=store_true)
- **Engine wiring**: Passes `enable_auto_winner_guard_allowlist` to constructor
- **Logging**: Added `[GATE] Auto Winner Guard Allowlist` config log
- **Config output**: Persisted in JSON results config section

### 3.3 Tests

Created `tests/phase35/test_auto_winner_guard_allowlist.py` with 31 tests:
- `TestDefaultOff` (4 tests): Verify flag is False by default, rejects non-bool
- `TestAllowlistExtension` (6 tests): Core logic — auto alphas pass/blocked
- `TestFallbackFilterExtension` (3 tests): Fallback filter also extends
- `TestEvidenceFields` (4 tests): New evidence fields populated correctly
- `TestCLIWiring` (6 tests): CLI flag exists and wires correctly
- `TestSourceInspection` (5 tests): Source code patterns verified
- `TestSerializeFoldDetails` (1 test): JSON serialization round-trip
- `TestBackwardCompatibility` (2 tests): No behavior change when disabled

**All 31 new tests passed. All 94 existing tests (33 OOS bundle + 61 winner guard) passed.**

## 4. 12-Fold Dynamic OOS Results

### Configuration (identical to baseline except allowlist flag)

| Parameter | Value |
|-----------|-------|
| n_folds | 12 |
| train_years | 3 |
| test_years | 1 |
| top_n_symbols | 30 |
| formulaic_alpha_set | v3_pruned |
| formulaic_winner_guard | true |
| enable_automated_oos_bundle | true |
| enable_auto_winner_guard_allowlist | **true** (new) |
| dynamic_universe | true |
| drawdown_control | true (threshold 10%) |

### Performance Comparison

| Metric | Baseline (auto blocked) | Allowlisted | Delta |
|--------|------------------------|-------------|-------|
| **Avg Portfolio IC** | 0.0149 | -0.0004 | -0.0153 |
| **Avg Portfolio Sharpe** | 3.0756 | 2.2783 | -0.7973 |
| **Avg Max Drawdown** | -12.11% | -12.09% | +0.02% |
| **Avg Raw Signal IC** | 0.0181 | 0.0187 | +0.0006 |
| **Avg Daily CS IC** | 0.0191 | 0.0212 | +0.0021 |
| **Total PnL (VND)** | 609M | 445M | -164M |

### Per-Fold Winner Guard Evidence (Allowlisted Run)

| Fold | post_guard_alphas (with allowlist) | Auto in post_guard? |
|------|-------------------------------------|---------------------|
| 1 | auto_mr_zscore_20, auto_rsi_14 | YES (2 auto) |
| 2 | auto_rsi_14, auto_mr_zscore_20 | YES (2 auto) |
| 3 | auto_mr_zscore_20 | YES (1 auto) |
| 4 | auto_vol_std_ratio_10_30, alpha_fml052 | YES (1 auto) |
| 5 | alpha_fml067, alpha_fml006, alpha_fml045, alpha_fml052, auto_vol_std_ratio_10_30, alpha_fml012 | YES (1 auto in fallback) |
| 6 | auto_mom_ret_60, alpha_fml052 | YES (1 auto) |
| 7 | auto_mom_ret_20, auto_rsi_14 | YES (2 auto) |
| 8 | auto_mom_ret_20, alpha_fml045, auto_mom_ret_60 | YES (2 auto) |
| 9 | auto_rsi_14 | YES (1 auto) |
| 10 | alpha_fml052 | NO (0 auto) |
| 11 | alpha_fml067, alpha_fml052 | NO (0 auto) |
| 12 | auto_vol_std_ratio_10_30 | YES (1 auto) |

### Analysis

The allowlist extension is **functionally correct** — auto alphas now pass
through the winner guard in 10/12 folds. However, the allowlisted configuration
**does not improve performance** vs the blocked baseline:

1. **Portfolio IC decreased** (0.0149 -> -0.0004): Auto alphas selected by the
   guard tend to be high-IC in train but less stable OOS. The winner guard
   was actually providing useful stability filtering.
2. **Sharpe decreased** (3.08 -> 2.28): Consistent with IC degradation.
3. **Max Drawdown unchanged** (-12.1% in both): Drawdown control dominates.
4. **Raw signal IC slightly improved** (0.0181 -> 0.0187): Auto alphas have
   marginally better raw IC, but portfolio construction doesn't benefit.

**Conclusion**: The winner guard's exclusion of auto alphas was protective,
not harmful. The allowlist is useful for research exploration but should
remain opt-in (default off).

## 5. Evidence Files

| File | Path |
|------|------|
| Allowlisted run results | `data/phase35_results/phase35_backtest_results_auto_wg_allowlist_20260615_baseline.json` |
| Allowlisted run summary | `data/phase35_results/phase35_backtest_summary_auto_wg_allowlist_20260615_baseline.txt` |
| Baseline (blocked) results | `data/phase35_results/phase35_backtest_results_automated_oos_bundle_20260615_baseline.json` |
| Test file | `tests/phase35/test_auto_winner_guard_allowlist.py` |

## 6. SOD Compliance

- [x] Implementation-only, no self-approval
- [x] Tests required, all passing (31 new + 94 existing = 125)
- [x] Default behavior unchanged (opt-in, backward compatible)
- [x] Evidence persisted in `.ly_state/session/`
- [x] PIT-safe: no future data used in allowlist logic
- [x] No live promotion
