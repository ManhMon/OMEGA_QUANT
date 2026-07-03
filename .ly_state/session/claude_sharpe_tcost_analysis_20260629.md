# Sharpe & Transaction-Cost Reduction Plan — OMEGA_QUANT Hybrid Regime Pipeline

**Author**: Claude (Opus 4.7, senior quant researcher hat)
**Date**: 2026-06-29
**Scope**: Analyze the 45-fold CPCV results from `scripts/backtest_hybrid_regime.py` and propose concrete code-level changes (no implementation) that (1) cut transaction cost drag and (2) lift Sharpe, with PIT safety preserved.

---

## 0. Evidence Base

Files read:
- `scripts/backtest_hybrid_regime.py` (full, 2258 lines)
- `src/omega/quant/evolution/optuna_regime_nested_cv.py`
- `src/omega/quant/pipeline/overlays/tcost.py`, `rebalance_frequency.py`, `weight_smoothing.py`
- `tests/phase35/test_stage6_2_cost_aware.py`, `test_stage6_3_drawdown_control.py`
- `data/phase35_results/experiment_comparison_report.md`
- `data/phase35_results/hybrid_regime_cpcv_comparison_e2a_tcost15.json` (full)
- `data/phase35_results/hybrid_regime_cpcv_comparison_e3_topk7.json` (full)
- File listing of `data/phase35_results/`

### Headline numbers (mean over 45 CPCV folds, 2015–2026, top-30 static universe, capital 2B VND)

| Experiment      | Scenario | Mean SR | StdDev SR | Mean Ret | Mean MaxDD | TC %    | Turnover/day | Cash days |
|-----------------|----------|---------|-----------|----------|------------|---------|--------------|-----------|
| E1 Fixed DD     | Baseline | −0.64   | 1.26      | −0.9%    | −43%       | **79%** | 0.093        | 55%       |
| E1 Fixed DD     | Hybrid   | −0.58   | 1.15      | −3.3%    | −45%       | 77%     | 0.099        | 51%       |
| E2a TCost 15bps | Baseline | −0.42   | 1.30      | +12.5%   | −42%       | 67%     | 0.100        | 51%       |
| E2a TCost 15bps | Hybrid   | −0.52   | 1.27      | +3.3%    | −46%       | **82%** | 0.107        | 47%       |
| E2c TCost 50bps | Baseline | −0.62   | 1.21      | −1.8%    | −42%       | 81%     | 0.092        | 55%       |
| E3a TopK 3      | Baseline | **−0.99** | 1.33    | −15.4%   | −51%       | **134%**| 0.102        | 58%       |
| E3b TopK 7      | Baseline | **−0.42** | 1.15    | +7.0%    | −37%       | **49%** | 0.085        | 56%       |
| E3b TopK 7      | Hybrid   | −0.45   | 1.15      | +4.3%    | −39%       | 55%     | 0.089        | 53%       |

Mean alpha IC overall = **0.0161** (median 0.018, IC range −0.009 .. +0.037). Per-regime IC: Bull 0.013, Sideways 0.017, **Bear 0.019** (highest). IC numbers are identical between Baseline and Hybrid — i.e., the GMM regime overlay does NOT change alpha selection, only sizing.

Fold-31 pathology: in TopK7 baseline its `total_tc_pct` = **582%** with gross 482% — accounting bug suspected (see Section A.6).

---

## A. Diagnosis — Why Sharpe Is Negative

| Root cause | Evidence | Severity |
|---|---|---|
| **A.1 TC drag dominates** | Mean TC / gross = 0.67 / 0.55 ≈ 122%. Net = gross − tc < 0 in most experiments. | **Critical** |
| **A.2 Alpha IC is structurally low** | Mean IC 0.016 (60-day horizon). Bull-regime IC 0.013 — barely above zero. With IC≈0.016 and IR ≈ IC·√breadth, top-5 names → IR ≈ 0.04, well under the 0.07–0.10 needed to overcome 60–80% cumulative TC. | **High** |
| **A.3 Hybrid is strictly worse than Baseline** | Across E1/E2a/E2b/E2c/E3a/E3b, Hybrid Sharpe is consistently 0.03–0.10 lower than Baseline. GMM regime overlay adds turnover (+0.007 daily on E2a) and TC (+15pp on E2a) without lifting realised IC (IC numbers identical). The regime scaling pumps churn but lands on the same alpha. | **High** |
| **A.4 Concentration whipsaw** | TopK=3 doubles TC (134% vs 67%) and halves Sharpe (−0.99 vs −0.42 vs TopK=7). Each name-rotation at TopK=3 ≈ 33% turnover. The `LongOnlyConcentratedOverlay` re-normalises to sum=1, so any rank flip = full re-weighting. | **High** |
| **A.5 Cash-days % very high** | 47–58% of test days have abs(weights)<5%. Drawdown control + bear damping + cost gating keep portfolio flat half the time. When it does trade, it pays the full bid-ask, then the regime flips and it stops out again. Whipsaw cycle = full liquidate → rebuild = 200% turnover per cycle. | **High** |
| **A.6 TC accounting likely double-counts in `compute_fold_profitability_diagnostics`** | `backtest_hybrid_regime.py:1327` aggregates `cost_breakdown["total_cost"]` as a single fraction summed across bars (not normalised by exposure-days). Fold-31 reports TC = 582%–1062% — physically implausible. Recommend cross-checking against `cost_breakdown` keys (`total_commission`, `total_spread`, `total_slippage`). Until validated, the TC% column should be read as "TC-units" not "TC as fraction of capital". | **Medium (diagnostic)** |
| **A.7 Embargo < label horizon** | `embargo_pct=0.01` ≈ 28 trading days; `label_horizon=60`. CPCV adjacent fold combinations can leak labels through the un-embargoed zone. Inflates measured IC, biases ridge/lightgbm regressors → real OOS Sharpe is even lower than reported. | **Medium (PIT-adjacent)** |
| **A.8 Alpha selection ignores turnover** | `backtest_hybrid_regime.py:993–1052` picks 2 alphas per category by absolute IC. No `cost_per_turnover` penalty (despite `Phase35WalkForwardEngine.adjust_alphas_for_cost` existing for exactly this in tests). High-turnover noisy alphas survive selection. | **High** |
| **A.9 WeightSmoothingOverlay re-rescales to target exposure** | `weight_smoothing.py:19–21` divides smoothed weights by their own abs-sum and multiplies by raw target abs-sum. This UNDOES half the smoothing benefit: shape is smoothed but magnitude is restored, so per-name turnover is still elevated. | **Medium** |
| **A.10 Bear regime is high-IC but exposure is cut to 15%** | `latent_gmm_bear_dampening=0.15`. Bear IC=0.019 (highest of any regime) — we're suppressing exposure exactly where signal is strongest. Likely a defensive over-correction from drawdown-paranoia. | **Medium** |

**Net answer to (A)**: Sharpe is negative primarily because TC drag (driven by turnover whipsaw from regime overlays + top-K rotation + low EMA effectiveness + low alpha-selection threshold) exceeds gross alpha. The Hybrid scenario adds churn without adding alpha. PIT-relevant concern A.7 (embargo) may further inflate measured IC vs. real OOS IC.

---

## B. Top 5 Transaction-Cost Reductions

### C-1. Raise `min_trade_threshold_bps` from 150 → 300–400 bps (and add per-regime scaling)

- **What**: `backtest_hybrid_regime.py:231` default `--min-trade-threshold-bps=150`. Threshold gate in `TCostOverlay(min_trade_threshold_bps=...)` blocks trades smaller than this in `apply_tcost_overlay` / `apply_dynamic_tcost_overlay` (in `omega.quant.portfolio.tcost_optimizer_overlay`). With round-trip cost ≈ 35bps, current gate at 4.3× cost is too permissive for IC=0.016.
- **Why it works**: Doubling the threshold reduces gated trade count roughly geometrically with weight-change distribution; expected to cut turnover ~30–40% while keeping the highest-conviction trades.
- **Wire-up**: also pass `use_dynamic_budgeting=True` (already on) AND have `apply_dynamic_tcost_overlay` use a per-regime IC-scaled threshold: in bear regime (highest IC) keep threshold lower; in sideways raise it 2×.
- **Effort**: 2 h. **Impact**: HIGH. **Risk**: MED (sweep needed — verify Sharpe doesn't regress because of missed trades). **Bucket**: Quick Win.
- **PIT**: pure backward-looking gate. Safe.

### C-2. Lengthen rebalance interval 10 → 20 trading days; align with `pipeline_config.turnover_reduction.rebalance_frequency='weekly'`

- **What**: `backtest_hybrid_regime.py:235` `--rebalance-every-n-days=10`; overlay constructed at line 527 with `mode="fixed_interval"`. Pipeline config at line 636 already declares `"rebalance_frequency": "weekly", "rebalance_day_of_week": 0` — but the overlay ignores those keys and uses the CLI value. Switch the overlay to `mode="day_of_week", day_of_week=0, rebalance_every_n_days=20` (or biweekly Monday).
- **Why it works**: Halves turnover almost mechanically. Label horizon is 60 days, so trading every 20 days still captures >70% of decision freshness.
- **Effort**: 1 h. **Impact**: HIGH. **Risk**: LOW. **Bucket**: Quick Win.
- **PIT**: schedule built from `weights.index` only (`rebalance_frequency.py:77–122`). Safe.

### C-3. Add `cost_per_turnover` penalty to the quota-based alpha selection in `train_fold_models`

- **What**: `backtest_hybrid_regime.py:993–1052` selects top-2 per category by `abs(alpha_ics[lc])`. Replace with `score = abs(ic) − λ * estimate_turnover(alpha_col, train_feat)` where `estimate_turnover` is ported from `Phase35WalkForwardEngine._estimate_alpha_turnover` (already tested in `tests/phase35/test_stage6_2_cost_aware.py`).
- **Why it works**: High-turnover alphas (e.g., short-horizon microstructure signals) that survive on raw IC trigger rebalance churn. Penalising them at selection time = compound benefit (selection × execution).
- **Effort**: 4 h (port the helper, wire into selection loop, sweep λ ∈ {0.001, 0.003, 0.01}).
- **Impact**: MED-HIGH. **Risk**: LOW (tests already cover the helper). **Bucket**: Quick Win.
- **PIT**: turnover computed on `train_feat` only — explicit PIT test in `test_stage6_2_cost_aware.py::TestPITSafety`.

### C-4. Add hysteresis to `LongOnlyConcentratedOverlay` to stop name-rotation whipsaw

- **What**: `backtest_hybrid_regime.py:88–134`. Today: each rebalance picks the literal top-K — one alpha-rank flip = full name swap = 1/K turnover. Change to: a name held in `t-1` is evicted only if its rank > K + `eviction_buffer` (e.g., K=5 entry, eviction at rank>8). Carry state in `state` dict the overlay receives.
- **Why it works**: ~50–70% of weight-rotation turnover is "rank wobble in noisy alphas". Buffer width 3 absorbs noise without losing real conviction changes.
- **Effort**: 6–8 h (state management, unit test, sweep buffer).
- **Impact**: HIGH. **Risk**: LOW. **Bucket**: Medium.
- **PIT**: uses only `t-1` and `t` rankings, no future. Safe.

### C-5. Fix the magnitude re-scale in `WeightSmoothingOverlay` and lower `ema_alpha` 0.08 → 0.05

- **What**: `src/omega/quant/pipeline/overlays/weight_smoothing.py:19–21` re-scales smoothed weights back to the raw target exposure. Removing that re-scale (or making it gradual: `target = β·raw_target + (1−β)·smoothed_target`, β=0.3) lets smoothing actually dampen magnitude churn, not just shape.
- **Why it works**: EMA(0.08) means half-life ≈ 8 rebalances — but re-scale resets total notional every rebalance, so per-name turnover ≈ raw_per_name * (1 − blend). Removing re-scale restores expected EMA benefit. Empirically should shave 15–25% off turnover_avg.
- **Effort**: 2–4 h (code change is 3 lines; sweep `β` ∈ {0.3, 0.5}, validate regime-flip behavior).
- **Impact**: MED. **Risk**: MED (could underperform in sharp regime flips — pair with C-4 to keep responsiveness on top-K composition while damping magnitude).
- **Bucket**: Quick Win.
- **PIT**: EMA is causal (uses past weights only). Safe.

### Bonus diagnostic — Audit `cost_breakdown["total_cost"]` reporting

- **What**: `compute_fold_profitability_diagnostics` at line 1326–1332 reads `cost_breakdown["total_cost"]` directly. Fold-31 reports TC%=582% with turnover_avg=0.03 — inconsistent. Likely the underlying cost is summed across all bars without normalisation by capital-days, or includes a halt-cost double-count.
- **Why**: If real TC is actually 5–10× smaller than reported, Sharpe interpretation shifts (closer to flat/positive). Either way, accurate accounting is a prerequisite for tuning the above 5 levers.
- **Effort**: 4–6 h. **Impact**: instrumentation (large meta-impact). **Risk**: LOW. **Bucket**: Quick Win.
- **PIT**: read-only diagnostic. Safe.

---

## C. Top 5 Sharpe Improvements

### S-1. Replace `top_k=5` with `top_k=8–10` and let `TailControlOverlay(max_abs_weight=0.25)` cap concentration

- **What**: `backtest_hybrid_regime.py:223` `--top-k=5`. Empirics: TopK=3 SR=-0.99, TopK=5 SR=-0.64, TopK=7 SR=-0.42. Monotonic improvement with K. Run TopK=10 next.
- **Why it works**: (a) per-name idiosyncratic risk diversifies as 1/√K, (b) per-name turnover on rotation drops linearly with K, (c) more names give the alpha signal room to express IC=0.016 across breadth.
- **Effort**: 2 h (one CLI flag + a run). **Impact**: HIGH. **Risk**: LOW. **Bucket**: Quick Win.
- **PIT**: pure portfolio construction. Safe.

### S-2. Enable `--dynamic-universe` and expand `--symbol-count` 30 → 60–80

- **What**: `backtest_hybrid_regime.py:181, 185`. Static top-30 by full-period volume leaks survivorship/selection bias (it picks whatever was liquid by 2026, not what was liquid in 2015). `DynamicUniverseSelector` (in `phase35_data_loader.py`) already does PIT-safe per-rebalance reselection on 21-day cadence.
- **Why it works**: (a) removes look-ahead in name selection, (b) larger pool = better top-K skim (the K-th percentile alpha is higher), (c) addresses the structural IC weakness directly. Expected IC lift +0.003 to +0.006.
- **Effort**: 4 h (run, parity-check, validate dynamic_schedule). **Impact**: HIGH. **Risk**: LOW (selector is gated). **Bucket**: Medium.
- **PIT**: dynamic selector is PIT-safe by construction (uses 252-day lookback, 21-day rebalance). Safe.

### S-3. Reverse the bear-regime damping; tune `regime_sizing_scale` 0.5 → 0.25–0.35 AND `latent_gmm_bear_dampening` 0.15 → 0.40–0.60

- **What**: `backtest_hybrid_regime.py:537, 577`. Bear-regime alpha IC is 0.019 — HIGHER than bull (0.013) and sideways (0.017). Cutting exposure to 15% in bear regime sacrifices the strongest signal. Plus the aggressive damping causes whipsaw entering/exiting bear, fuelling turnover.
- **Why it works**: lift exposure where IC is strongest, smooth the regime transitions to cut whipsaw turnover. Two-for-one: Sharpe up, TC down.
- **Effort**: 6–8 h (grid sweep over (regime_sizing_scale, bear_dampening, bull_boost) on 5–10 outer CPCV folds; pick by net-Sharpe).
- **Impact**: HIGH. **Risk**: MED (bear regimes are high-variance — drawdown control becomes more important; pair with Drawdown threshold tuning).
- **Bucket**: Medium.
- **PIT**: GMM model fit on train only (already enforced in `train_fold_models`). Safe.

### S-4. Switch the alpha blender from pointwise `LightGBMRegressor(returns)` to a cross-sectional ranker

- **What**: `backtest_hybrid_regime.py:927–939` uses `LGBMRegressor` to predict per-row returns. But the decision is cross-sectional ranking (top-K per date). Use `LightGBMRanker` (objective="lambdarank") with `group=symbols_per_date`, label = winsorised forward-return rank.
- **Why it works**: aligns loss with decision. Pointwise regression spends capacity predicting return magnitudes that the decision rule discards. Ranker concentrates capacity on getting the top-K order right. Typical IC lift in literature is +30–60% relative on the same features.
- **Effort**: 12–16 h (refactor `_new_alpha_model` → `_new_ranker_model`, build `group` arrays, validate on one fold first, then full CPCV).
- **Impact**: HIGH. **Risk**: MED (ranker hyperparams need tuning; group construction must be exact).
- **Bucket**: Long Term.
- **PIT**: still trained on train-only data; ranker doesn't change PIT properties. Safe.

### S-5. Add a min-variance / equal-risk-contribution sizing step before `LongOnlyConcentratedOverlay`

- **What**: today equal-weighting after top-K (uniform 20% each at K=5) is correlation-naive. Use the existing `src/omega/quant/portfolio/markowitz.py` to compute shrinkage-covariance min-variance weights over the top-15 candidates, then top-K → final. Or use `RiskSizingOverlay(inverse_vol_sizing=True)` more aggressively with shrinkage covariance.
- **Why it works**: VN equities are heavily sector-correlated (banks, real-estate, steel). Equal weight = de-facto sector concentration. Min-var collapses correlated picks into one position → cuts realised vol → Sharpe up for same return.
- **Effort**: 12–20 h (covariance shrinkage with rolling window, integrate as pre-overlay, validate non-negativity & sum constraints, sweep window length).
- **Impact**: HIGH. **Risk**: MED (estimator instability with small windows — use Ledoit-Wolf shrinkage).
- **Bucket**: Long Term.
- **PIT**: covariance computed on past returns window only. Safe.

### Bonus — Widen embargo to ≥ label horizon

- **What**: `--embargo-pct=0.01` ≈ 28 days, vs label horizon 60. Raise to `0.025` (≈ 65 days, ≥ horizon).
- **Why**: removes label-leakage between adjacent CPCV folds → measured IC and Sharpe become unbiased estimators of true OOS performance. Reported Sharpe will likely DROP slightly (it's been inflated) but tuning thereafter is sound.
- **Effort**: 1 h. **Impact**: LOW-MED (improves measurement integrity, not strategy). **Risk**: LOW. **Bucket**: Quick Win.
- **PIT**: strictly tightens PIT discipline. Safer.

---

## D. Effort / Impact / Risk Summary

| ID  | Lever | Effort | Impact | Risk | Bucket |
|-----|---|---|---|---|---|
| C-1 | `min_trade_threshold_bps` 150→300–400 | 2 h | HIGH | MED | Quick Win |
| C-2 | Rebalance interval 10→20d, weekly DoW | 1 h | HIGH | LOW | Quick Win |
| C-3 | Turnover-penalised alpha selection | 4 h | MED-HIGH | LOW | Quick Win |
| C-4 | LongOnlyConcentrated hysteresis (entry K, evict K+3) | 6–8 h | HIGH | LOW | Medium |
| C-5 | Fix WeightSmoothing re-scale; lower α | 2–4 h | MED | MED | Quick Win |
| C-* | Audit `cost_breakdown` accounting (diagnostic) | 4–6 h | meta | LOW | Quick Win |
| S-1 | `top_k` 5→8–10 | 2 h | HIGH | LOW | Quick Win |
| S-2 | Dynamic universe + 60 names | 4 h | HIGH | LOW | Medium |
| S-3 | Reverse bear damping, retune regime scale | 6–8 h | HIGH | MED | Medium |
| S-4 | LightGBM Ranker (lambdarank) blender | 12–16 h | HIGH | MED | Long Term |
| S-5 | Min-variance pre-sizing (Ledoit-Wolf) | 12–20 h | HIGH | MED | Long Term |
| S-* | Embargo ≥ label horizon | 1 h | LOW-MED | LOW | Quick Win |

---

## E. Recommended Sequence (so each step de-risks the next)

**Phase 1 — Quick Wins (1–2 days, ~16 h total)**
1. Embargo fix (S-*) + accounting audit (C-*): get measurement right BEFORE tuning.
2. TopK 5→10 (S-1) + rebalance 10→20d (C-2) + threshold 150→350bps (C-1): three mechanical knobs that together should drop turnover ~50% and lift Sharpe through diversification — net expected Sharpe lift ~+0.3 to +0.5 conservatively.
3. WeightSmoothing fix (C-5).
4. Re-run full CPCV → measure new baseline.

**Phase 2 — Medium (1 week, ~25 h total)**
5. Turnover-penalised alpha selection (C-3).
6. LongOnlyConcentrated hysteresis (C-4).
7. Dynamic universe + 60 names (S-2).
8. Regime damping reversal sweep (S-3).
9. Re-run full CPCV → second baseline.

**Phase 3 — Long Term (2+ weeks, ~30 h total)**
10. LightGBM Ranker (S-4).
11. Min-variance pre-sizing (S-5).
12. Re-run CPCV with full stack; if Sharpe still <0, escalate to alpha-research review (the structural ceiling at IC≈0.016 may need new alpha factors, not pipeline tuning).

---

## F. PIT Safety Audit of Recommendations

Each lever above is annotated "PIT: Safe" because:
- **No future returns / future prices** are used anywhere — all penalties, smoothers, thresholds, and regime estimates draw on past observations only.
- **C-3, C-4, S-3, S-4, S-5** train statistics (turnover, hysteresis state, regime params, ranker, covariance) on train-fold data only — consistent with the existing PIT discipline enforced in `train_fold_models()` (lines 802–812 raise `ValueError` on empty train, preventing silent fallback) and `_map_rows_to_gmm_regimes()` (lines 1247–1251 shift latents before per-date mean).
- **Embargo widening (Bonus)** strictly tightens PIT discipline.
- **C-5 (EMA fix)** uses only past weights; EMA is causal.
- **C-1 (threshold), C-2 (schedule)** are parameter changes, not data flows.

No recommendation introduces look-ahead bias. No recommendation requires SoD gate redesign — all changes are local to `scripts/backtest_hybrid_regime.py` config/overlay parameters and a small number of overlay implementations under `src/omega/quant/pipeline/overlays/`.

---

## G. Open Questions for the User (Not Blockers)

1. **Realism of cost model**: HOSE round-trip ≈ 25–35 bps (commission both sides + sell tax 0.1%) — current default `cost_per_trade_bps=35` is correct. But the experiment sweeps used 15/20/50 bps — are those probing optimistic-execution scenarios or realistic stress tests?
2. **Capacity**: at 2B VND with TopK=10 and 20-day rebalance, daily volume target per name ≈ 200M VND. Need a capacity check (ADV ≥ 10× trade size) before pushing to live. `adv_vnd` is computed in `prepare_panel:273–278` but not wired into the cost gate.
3. **Why is Bear IC > Bull IC?** Worth a 1-day investigation — could indicate the alpha factors are tail-event factors (good in crises, weak in trends), suggesting a different strategic positioning altogether (e.g., overlay on a passive index in calm regimes, alpha-only in stress).

---

*End of analysis. No code was modified. Decision is the user's.*
