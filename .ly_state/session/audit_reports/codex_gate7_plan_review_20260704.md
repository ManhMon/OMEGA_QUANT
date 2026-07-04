# Codex Architectural Review - Gate 7 Plan

Review target: `.ly_state/session/gate7_neutralization_liquidity_plan.md`

Parent context: `.ly_state/session/gp_improvement_plan_20260703.md`

Code inspected:
- `scripts/genetic_alpha_evolution_v3.py`
- `src/omega/quant/evolution/genetic_engine.py`

## 1. Technical Soundness Assessment

Phase 2 concept is directionally correct: neutralized IC should compare residual alpha vs residual target after per-date regression on size and sector controls.

Blocking gap: current engine already has `_neutralize_cross_section`, `_compute_time_fold_ir`, and batch neutralization, but it neutralizes alpha only. In `genetic_engine.py:820-827`, time-fold IR delegates to `_compute_time_fold_ir`; inside that path `genetic_engine.py:244-258` neutralizes `alpha_fold` only. The pooled path at `genetic_engine.py:829-836` also neutralizes only `alpha_series`. The Gate 7 plan says residualize both alpha and target, but does not call out this existing alpha-only implementation or the batch path at `genetic_engine.py:1398-1407`. L2 could implement the plan literally in one path and leave the active fast path wrong.

The OLS design needs a rank/DOF guard, not only `neutralize_min_cross_section=8`. With top-N PIT universes and many sector dummies, rows can be fewer than `X_cols + 1`. The parent plan mentions this; the Gate 7 plan only partially covers it.

Sector mapping is technically better than the current volume-quartile proxy in `genetic_alpha_evolution_v3.py:127-131`, but the proposed fallback `ticker.str[0]` is not acceptable. It creates arbitrary pseudo-sectors and can inject structure unrelated to economic sectors. Fallback should be `Unknown` or size-only neutralization.

Phase 4 concept is correct, but units are ambiguous. The plan names `--min-avg-volume` as VND while computing rolling mean of raw `volume`. If `volume` is shares, threshold semantics are wrong. Use trailing average traded value (`close * volume`) if the threshold is VND, or rename/help it as shares.

## 2. Integration Risk Analysis

High integration risk with current Gate 6 state.

The plan assumes Gate 6 K=3 fold IR is complete, but current script config sets `use_time_fold_ir=True` and `time_folds=8` at `genetic_alpha_evolution_v3.py:658-661`. `GPConfig` default is `time_folds=3` at `genetic_engine.py:530-533`, but V3 overrides it. Gate 7 must explicitly restore or preserve K=3 if that is the gate contract.

Validation and model selection still use raw daily IC diagnostics in `genetic_alpha_evolution_v3.py:690-693`, then sort by `val_IC_daily` at `genetic_alpha_evolution_v3.py:725`. These metrics do not use engine-consistent fold IR, neutralization, or liquidity filtering. The parent plan required test IC to match training semantics; Gate 7 omits this. That means training can optimize neutralized/liquid fold IR while selected alphas are ranked by raw unfiltered validation IC.

Liquidity must be centralized in an evaluation mask. Current `_score_alpha_series` observation count uses only `pd.notna(target)` at `genetic_engine.py:647-655`; adding a mask only inside `_compute_combined_ic` leaves min-observation gating and coverage inconsistent.

Existing random row subsampling is correctly bypassed for `use_time_fold_ir=True` at `genetic_engine.py:1347-1359`. Gate 7 should not reintroduce random row sampling before fold construction.

## 3. PIT Safety Verification

Feature lagging in current script is mostly PIT-safe: terminals are shifted at `genetic_alpha_evolution_v3.py:129`, log traded-value proxy at `genetic_alpha_evolution_v3.py:130`, and current sector proxy at `genetic_alpha_evolution_v3.py:131`.

Liquidity rolling implementation in the plan is PIT-safe only if the shift is done per ticker after rolling. The shorthand `df.groupby("ticker")["volume"].rolling(...).mean().shift(1)` can shift across ticker groups after the rolling result is materialized. The expanded implementation with `reset_index(...).groupby("ticker").shift(1)` is the safer form and should be mandatory.

Sector mapping PIT safety is unproven. A static `data/sector_mapping_level2.csv` exists and has `symbol,sector`, but the plan must state provenance: sector labels must be as-of-invariant for the research period or versioned by date. A current-sector file can leak future classifications, mergers, or reclassifications.

Neutralization itself does not look ahead if controls are T-1 and regression is per date. But target residualization must use only same-date controls known before return realization. That is acceptable for neutralized IC attribution, not for creating tradable labels.

## 4. Implementation Feasibility

Implementable by L2, but the plan is not precise enough against the current code.

Minimum viable implementation should modify existing engine paths instead of adding parallel helpers:
- Add one `_evaluation_mask(alpha, target, features)` and use it in `_score_alpha_series`, pooled IC, ICIR, time-fold IR, multi-target IC, and tests.
- Extend `_neutralize_cross_section` or add a small wrapper that residualizes any `values` array under a supplied mask, then call it for both alpha and target.
- Update batch neutralization so alpha and target are scored consistently, or disable batch neutralization when target residualization/liquidity masking is enabled.
- Update V3 script to pass `__liquidity_mask__` for train/val/oos/lockbox, not only train/test.
- Replace raw validation scoring at `genetic_alpha_evolution_v3.py:690-693` with an engine-consistent scoring helper.
- Set `time_folds=3` unless Gate 6 contract was intentionally changed to 8.

Tests proposed by the plan are useful but too weak. They should assert target residualization, liquidity-aware min observation rejection, all scoring paths, and current V3 config defaults. Tests should live near existing genetic engine tests unless there is a repo convention requiring separate files.

## 5. Recommendations

Revise Gate 7 plan before L2 dispatch.

Blocking revisions:
- State that both alpha and target must be residualized in every active path, including current time-fold IR and batch-neutralized evaluation.
- Add centralized liquidity/evaluation mask and require observation thresholds after liquidity filtering.
- Fix V3 fold contract: `time_folds=3` or document and approve the current `time_folds=8` deviation.
- Make validation/model-selection scoring engine-consistent with training semantics.
- Resolve volume units: shares vs VND traded value.
- Remove pseudo-sector fallback based on ticker prefix.
- Require sector mapping PIT provenance or degrade to size-only/Unknown sectors.
- Require ticker-local rolling shift for liquidity; no global shift after grouped rolling.

Non-blocking improvements:
- Prefer real market cap if available; otherwise name `log(close * volume)` as traded-value/liquidity proxy, not market cap.
- Guard OLS with `n_rows > n_design_cols` and rank checks.
- Log liquidity exclusion rate per split and fail/warn if too many rows are removed.

## 6. VERDICT: [NEEDS_REVISION]

Gate 7 plan is directionally sound, but not L2-ready. Blocking issues are target residualization coverage, liquidity mask centralization, Gate 6 K mismatch, raw validation ranking, liquidity unit ambiguity, unsafe sector fallback, and unproven sector PIT provenance.
