# L2 Implementation State — Role 14 (Data Scientist)
# GATE: FORMULAIC_ALPHA_V2_20260614
# Date: 2026-06-14
# Agent: OpenCode L2 Implementation Work

## Task Summary
Implement Formulaic Alpha Set v2 (research-only opt-in), focusing on mean
reversion / liquidity / volume-price families, based on CPCV12 formulaic
results. Excludes weak momentum (alpha_fml001 negative IC).

## Gate
- FORMULAIC_ALPHA_V2_20260614

## Files Modified
1. `src/omega/quant/alpha/formulaic_alphas.py` — Added v2 alpha set
   "mean_reversion_liquidity" with 8 PIT-safe candidates (4 retained from v1,
   4 new). Added GATE_ID_V2 constant. Updated compute_formulaic_alphas to
   handle v2 set. Updated metadata.
2. `scripts/run_phase35_backtest.py` — Added "mean_reversion_liquidity" to
   --formulaic-alpha-set CLI choices. Default unchanged ("small").
3. `tests/phase35/test_formulaic_alpha_adapter.py` — Added 9 new test classes
   (30 tests) covering v2 registry, finite outputs, PIT guards, CLI choice,
   default unchanged, determinism, metadata, naming, family coverage.

## V2 Alpha Set: "mean_reversion_liquidity" (8 candidates)
| # | Name | Family | Source |
|---|------|--------|--------|
| 1 | alpha_fml006_vp_corr_10 | volume_price | v1 retained |
| 2 | alpha_fml012_mean_rev_rank_10 | mean_reversion | v1 retained (best: IC 0.0104, 75% pos) |
| 3 | alpha_fml033_vol_vol_interact_10 | volatility_volume | v1 retained |
| 4 | alpha_fml045_liq_turnover_5 | liquidity | v1 retained (IC 0.0091, 66.7% pos) |
| 5 | alpha_fml052_close_zscore_mr_20 | mean_reversion | NEW v2 |
| 6 | alpha_fml067_vol_price_diverge_10 | volume_price | NEW v2 |
| 7 | alpha_fml078_range_compression_10 | mean_reversion | NEW v2 |
| 8 | alpha_fml089_amihud_illiq_20 | liquidity | NEW v2 |

Excluded: alpha_fml001_ts_rank_momentum_20 (negative IC in CPCV12)

## PIT Safety Compliance
- All v2 alphas use shift(1) minimum (T-1 lag)
- No negative shifts anywhere
- All rolling windows use positive min_periods
- Inf/NaN sanitized via _sanitize() on output
- Deterministic given same input

## Test Results
- 71/71 tests PASSED (pytest)
- Coverage: v2 registry, finite outputs, PIT guards, CLI choice, default
  unchanged, determinism, metadata, naming, family coverage

## Smoke Test (formulaic_v2_smoke)
- Quick-mode: 1 symbol, 2 folds
- All 8 v2 alphas computed successfully
- Output: data/phase35_results/phase35_backtest_results_formulaic_v2_smoke_baseline.json

## Full CPCV12 Run (cpcv12_formulaic_v2)
- 12 folds, 30 symbols, 3 train-years, 1 test-year
- All 8 v2 alphas computed, no errors
- Results:
  - Avg Portfolio IC: 0.0037
  - Avg Raw Signal IC: 0.0083
  - Avg Raw Signal Daily CS IC: 0.0110
  - Avg Portfolio Sharpe: 1.7907
  - Avg Max Drawdown: -68.72%
- V2 Alpha IC Summary:
  - alpha_fml052_close_zscore_mr_20: 0.0164 (positive)
  - alpha_fml012_mean_rev_rank_10: 0.0104 (positive, consistent)
  - alpha_fml045_liq_turnover_5: 0.0091 (positive, consistent)
  - alpha_fml067_vol_price_diverge_10: 0.0080 (positive, new)
  - alpha_fml006_vp_corr_10: 0.0059 (positive, consistent)
  - alpha_fml033_vol_vol_interact_10: 0.0043 (positive)
  - alpha_fml078_range_compression_10: -0.0100 (slightly negative)
  - alpha_fml089_amihud_illiq_20: -0.0610 (negative, needs investigation)
- Output: data/phase35_results/phase35_backtest_results_cpcv12_formulaic_v2_baseline.json

## Default Behavior
- DEFAULT_FORMULAIC_ALPHA_SET remains "small" (unchanged)
- enable_formulaic_alphas defaults to False (unchanged)
- No live/default pipeline behavior change

## Forbidden Path Scan
No forbidden paths accessed:
- .gemini/antigravity-ide/scratch/ag-kit: NOT accessed
- .openclaw/skills: NOT accessed
- C:\Users\GHC\.agents: NOT accessed
- .codex/memories: NOT accessed

## Repo-Local Files Read (Authoritative Sources)
1. `.agents/agent/data-scientist.md` — Role 14 agent definition
2. `.agents/skills/python-patterns/SKILL.md`
3. `.agents/skills/clean-code/SKILL.md`
4. `.agents/skills/testing-patterns/SKILL.md`
5. `.agents/skills/systematic-debugging/SKILL.md`
6. `.agents/skills/performance-profiling/SKILL.md`
7. `.agents/skills/quant-research/SKILL.md`
8. `.agents/skills/vietnam-market-data/SKILL.md`
9. `.agents/skills/backtesting-pit-safety/SKILL.md`
10. `.agents/skills/data-science-workflow/SKILL.md`

## Status
- Implementation: COMPLETE
- Tests: 71/71 PASSED
- Smoke run: COMPLETE (formulaic_v2_smoke)
- Full CPCV12 run: COMPLETE (cpcv12_formulaic_v2)
- Tier 3 audit submission: PENDING (not self-approved per SOD)
