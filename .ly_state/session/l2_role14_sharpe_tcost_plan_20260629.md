# L2 Research Report: Sharpe + Transaction Cost Improvement Plan

- Gate: `SHARPE_TCOST_IMPROVEMENT_PLAN_20260629`
- Role: `14 data-scientist`
- Scope: analysis only; no prod code changes
- Date: `2026-06-29`

## Repo-Local Role/Skill Files Read

- .agents/agent/data-scientist.md
- .agents/skills/python-patterns/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/systematic-debugging/SKILL.md
- .agents/skills/performance-profiling/SKILL.md
- .agents/skills/quant-research/SKILL.md
- .agents/skills/vietnam-market-data/SKILL.md
- .agents/skills/backtesting-pit-safety/SKILL.md
- .agents/skills/data-science-workflow/SKILL.md


## Forbidden Path Scan Result

- No authoritative role/skill loading from forbidden paths.
- Not used (non-authoritative): `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.


## Source Files Reviewed

- `scripts/backtest_hybrid_regime.py`
- `src/omega/quant/evolution/optuna_regime_nested_cv.py`
- `src/omega/quant/portfolio/tcost_optimizer_overlay.py`
- `src/omega/quant/pipeline/overlays/tcost.py`
- `src/omega/quant/pipeline/overlays/rebalance_frequency.py`
- `src/omega/quant/pipeline/overlays/weight_smoothing.py`
- `src/omega/quant/alpha/phase35.py`
- `tests/phase35/test_stage6_2_cost_aware.py`
- `tests/phase35/test_stage6_3_drawdown_control.py`
- Result summaries under `data/phase35_results/`, incl:
  - `hybrid_regime_cpcv_comparison.json`
  - `hybrid_regime_cpcv_comparison_e1_fixed_dd.json`
  - `hybrid_regime_cpcv_comparison_e2a_tcost15.json`
  - `hybrid_regime_cpcv_comparison_e3_topk3.json`
  - fold-level files such as `hybrid_fold11_Hybrid_e1_fixed_dd.json`, `hybrid_fold11_Hybrid_e2a_tcost15.json`, `hybrid_fold11_Hybrid_e3_topk3.json`, `hybrid_fold11_Hybrid_e4b_tcost20.json`

## Test Evidence

- Ran: `pytest tests/phase35/test_stage6_2_cost_aware.py tests/phase35/test_stage6_3_drawdown_control.py`
- Result: `26 passed`

## 1. Current System Diagnosis

### 1.1 Where Sharpe is currently lost

Primary finding: current losses are not from one lever; they stack.

1. Gross alpha is too weak/inconsistent.
- `hybrid_regime_cpcv_comparison.json` reports `mean_alpha_ic_overall ~= 0.0134` for both Baseline and Hybrid.
- This is below the repo skill target (`IC > 0.02 net of costs`), so the system starts with marginal signal quality.
- Regime segmentation does not rescue this materially; per-regime IC is modest, noisy, unstable.

2. Cost drag is very large in bad folds.
- In `hybrid_regime_cpcv_comparison.json`, Hybrid `mean_total_tc_pct ~= 1.958`, max `~9.047`; Baseline similar.
- In `hybrid_regime_cpcv_comparison_e1_fixed_dd.json`, Baseline `max_total_tc_pct ~= 11.166`.
- Fold file `hybrid_fold11_Hybrid_e1_fixed_dd.json` shows `total_turnover ~= 73.03`, `avg_cost_per_bar_bps ~= 47.09`.
- Top-k concentration worsens this: `hybrid_fold11_Hybrid_e3_topk3.json` has `total_turnover ~= 88.48`, `avg_cost_per_bar_bps ~= 70.10`, Sharpe `-3.46`.

3. Regime logic reduces exposure, but not enough bad trading.
- Hybrid often has lower turnover/exposure than Baseline in quick summary (`mean_turnover_avg 0.0419` vs `0.0614`; `mean_exposure_avg 0.2445` vs `0.3855`), but `mean_sharpe` is still worse (`-1.381` vs `-1.124`).
- Interpretation: regime overlay is de-risking, but not improving alpha discrimination enough. It may be suppressing exposure without removing poor trades in noisy regimes.

4. Selection/construction can amplify churn.
- Overlay stack in `scripts/backtest_hybrid_regime.py` is already defensive: rebalance gating, smoothing, TCost overlay, drawdown control.
- Yet concentrated selection (`LongOnlyConcentratedOverlay(top_k=...)`) plus later overlays can still induce large weight jumps when ranks reshuffle.
- Evidence: top-k=3 variant materially degrades Sharpe and drawdown vs broader versions.

5. Cost model/selection objective likely underprices real VN trading friction in alpha selection stage.
- In `src/omega/quant/alpha/phase35.py`, cost-aware alpha selection uses `adjusted_ic = raw_ic - cost_per_turnover * turnover` with default scalar `cost_per_turnover`.
- `_estimate_alpha_turnover()` is rank-change based, not execution-aware, ADV-aware, spread-aware, or board-lot-aware.
- This is directionally useful but too coarse, so high-churn alphas can still pass if raw IC is slightly better.

6. Sharpe metric in one path is arithmetic-sum based, not compounded.
- `phase35.py:4959` sets `total_return = daily_series.sum()` after cost subtraction.
- This does not directly break Sharpe, but it distorts return attribution/optimization feedback vs compounded reality.
- Could encourage parameter choices that look acceptable in arithmetic aggregation but are fragile under path-dependent compounding and drawdown.

### 1.2 Where transaction costs are currently lost

1. Too many weight changes even after gating.
- `TCostOverlay` suppresses only small deltas under a threshold.
- `apply_cost_aware_rebalance()` in `tcost_optimizer_overlay.py` compares absolute weight deltas to threshold; it does not estimate expected incremental alpha per trade or per-name capacity.

2. Dynamic threshold logic is based on rolling IC of portfolio weights, not direct trade profitability.
- `compute_rolling_ic()` uses shifted weights vs realized returns as proxy signal quality.
- This can misclassify whether current rebalance opportunity is worth paying cost.

3. Parameter set still aggressive.
- Backtest config defaults: `cost_per_trade_bps=35`, `min_trade_threshold_bps=150`, `rebalance_every_n_days=10`, smoothing alpha `0.08`, `top_k=5`.
- Result files show cost still dominates in several folds, so current thresholds are not tight enough for weak alpha regimes.

4. Concentration increases turnover and slippage.
- Fewer names => larger per-name weight swings, more board-lot rounding loss, more impact in thinner VN names.
- `top_k=3` results are strong evidence.

5. Static universe / limited liquidity adaptivity.
- Main runs reviewed are `dynamic_universe=false`.
- This likely leaves the system trading names whose current liquidity regime deteriorated, increasing slippage and failure cost.

## 2. Research Answers

### A. Where does the system currently lose Sharpe?

Ranked diagnosis:

1. Weak gross alpha quality (`mean_alpha_ic_overall ~= 0.0134`).
2. High cost drag in worst folds (`total_tc_pct` spikes to ~9-11x notional-equivalent drag in diagnostics).
3. Concentrated portfolio construction creating lumpy weight jumps and slippage.
4. Regime switching that reduces exposure but does not sufficiently improve trade selection quality.
5. Coarse cost-aware alpha ranking in `phase35.py` and coarse trade gating in `tcost_optimizer_overlay.py`.

### B. Top 3-5 concrete changes to reduce transaction costs

1. Tighten trade admission from delta-threshold to expected-net-alpha threshold.
2. Add hard turnover budget per rebalance / per month with carry-forward unmet changes.
3. Lengthen effective holding period in weak regimes via regime-conditional rebalance frequency.
4. Replace static concentration (`top_k`) with softer capacity-aware weight taper.
5. Use dynamic universe / liquidity gate at rebalance dates to avoid low-ADV names.

### C. Top 3-5 concrete changes to increase Sharpe

1. Net-of-cost alpha selection objective with IC decay + regime stability gating.
2. Better regime usage: trade less in low-confidence regimes, not just lower exposure.
3. Regime-conditional factor blending rather than one blended signal for all states.
4. Capacity-aware position sizing and softer concentration to reduce idiosyncratic drawdowns.
5. Drawdown control refinement using net expected recovery, not just realized loss state.

## 3. Prioritized Improvement Proposals

### Quick Wins (1-2 days)

#### QW1. Raise friction against marginal trades
- Change: increase `min_trade_threshold_bps`; test `150 -> 200/250`, and `rebalance_every_n_days` `10 -> 15`; keep weekly/monthly variants in sweep.
- Why: current results show cost drag still too high despite gating.
- Effort: `4-6h`
- Expected Sharpe improvement: `med`
- Transaction cost reduction: `high`
- Risk: `low`
- Evidence: cost-heavy variants improve when costs tightened; `top_k=3` proves the strategy is fragile to turnover.

#### QW2. Disable overly concentrated `top_k=3` style configs; bias toward broader books
- Change: standardize search around `top_k=5..10`, or use weight taper rather than hard truncation.
- Why: `hybrid_regime_cpcv_comparison_e3_topk3.json` materially worsens Sharpe, drawdown, turnover.
- Effort: `2-4h`
- Expected Sharpe improvement: `med`
- Transaction cost reduction: `med-high`
- Risk: `low`

#### QW3. Make alpha selection gate on net IC + turnover ceiling
- Change: in `phase35.py`, require alpha candidates to pass both adjusted IC and turnover cap; reject/high-penalize high-turnover alphas even if raw IC is slightly higher.
- Why: current `raw_ic - scalar*turnover` is too permissive and not capacity-aware.
- Effort: `6-10h`
- Expected Sharpe improvement: `med`
- Transaction cost reduction: `med`
- Risk: `low-med`

#### QW4. Turn on dynamic universe for research runs
- Change: compare `dynamic_universe=true` vs static universe using same CPCV setup.
- Why: reduce exposure to temporarily illiquid names; better VN market realism.
- Effort: `4-8h`
- Expected Sharpe improvement: `low-med`
- Transaction cost reduction: `med`
- Risk: `low-med`

### Medium Term (1 week)

#### MT1. Replace delta-threshold trading with expected-net-benefit trading
- Change: in `apply_cost_aware_rebalance()`, trade only when `expected_alpha_gain - estimated_cost > 0`, where expected gain uses signal delta / rank edge and estimated cost uses ADV/spread/board-lot-aware approximation.
- Why: current rule looks only at weight delta magnitude, not expected payoff.
- Effort: `16-24h`
- Expected Sharpe improvement: `high`
- Transaction cost reduction: `high`
- Risk: `med`

#### MT2. Regime-conditional rebalance schedule
- Change: in bull/high-IC regimes allow current cadence; in sideways/bear/low-IC regimes rebalance less often and widen no-trade bands.
- Why: current regime logic mostly scales exposure; it should also scale turnover appetite.
- Effort: `12-18h`
- Expected Sharpe improvement: `med-high`
- Transaction cost reduction: `high`
- Risk: `med`

#### MT3. Regime-conditional alpha ensemble selection
- Change: compute IC/IR/decay by regime; maintain separate alpha subsets or weights for bull/sideways/bear instead of one global ranking.
- Why: current overall IC is weak; regime-specific alpha persistence likely differs more than current stack exploits.
- Effort: `20-30h`
- Expected Sharpe improvement: `high`
- Transaction cost reduction: `med`
- Risk: `med`

#### MT4. Capacity-aware soft concentration
- Change: replace hard top-k truncation with softmax/rank taper plus max participation / ADV cap / board-lot penalty.
- Why: hard truncation amplifies churn and single-name weight jumps.
- Effort: `14-22h`
- Expected Sharpe improvement: `med-high`
- Transaction cost reduction: `med-high`
- Risk: `med`

### Long Term (2+ weeks)

#### LT1. Full VN microstructure cost model in selection + backtest objective
- Change: unify alpha ranking, overlay gating, and realized backtest around one cost model including board-lot rounding, ADV-tiered spread, price-limit exit haircut, foreign-room haircut, settlement drag.
- Why: current pipeline has pieces of this in diagnostics but not a single optimization objective.
- Effort: `40-60h`
- Expected Sharpe improvement: `high`
- Transaction cost reduction: `high`
- Risk: `high`

#### LT2. Deflated-Sharpe / CPCV model selection across strategy variants
- Change: promote variants by deflated Sharpe + OOS CPCV distribution, not mean Sharpe alone.
- Why: current result set shows very wide fold dispersion and occasional huge positive/negative outliers.
- Effort: `20-32h`
- Expected Sharpe improvement: `med-high`
- Transaction cost reduction: `low-med`
- Risk: `med`

#### LT3. Regime model redesign: confidence-calibrated switching
- Change: evaluate whether HMM/GMM/BOCPD stack should output regime confidence and switch only above certainty thresholds with hysteresis + turnover penalty in objective.
- Why: current hybrid de-risks but does not clearly outperform baseline.
- Effort: `40-80h`
- Expected Sharpe improvement: `high`
- Transaction cost reduction: `med`
- Risk: `high`

## 4. Best 5 Proposals With Effort / Impact / Risk

| Proposal | Goal | Effort | Sharpe Impact | Risk |
|---|---|---:|---|---|
| Raise trade threshold + slower rebalance cadence | Reduce churn | 4-6h | Med | Low |
| Net IC + turnover-cap alpha gating | Better alpha selection | 6-10h | Med | Low-Med |
| Expected-net-benefit trade admission | Reduce waste trades | 16-24h | High | Med |
| Regime-conditional alpha ensemble | Increase gross Sharpe | 20-30h | High | Med |
| Capacity-aware soft concentration | Lower slippage + drawdown | 14-22h | Med-High | Med |

## 5. Recommended Implementation Order

1. Parameter sweep quick win.
- Re-run CPCV with:
  - `min_trade_threshold_bps`: `150, 200, 250`
  - `rebalance_every_n_days`: `10, 15, 20`
  - `top_k`: `5, 7, 10`
  - `dynamic_universe`: `false/true`
- Goal: establish whether Sharpe improves mainly through lower turnover vs better breadth.

2. Tighten alpha admission.
- Add turnover ceiling + adjusted-IC gate in `phase35.py` research path.
- Goal: remove high-churn weak-edge alphas before portfolio construction.

3. Upgrade trade gate from delta-size threshold to net-benefit threshold.
- Use estimated alpha edge minus estimated cost.
- Goal: stop paying costs for low-conviction rebalances.

4. Add regime-conditional rebalance + alpha subsets.
- Goal: in low-confidence / sideways / bear regimes, trade less and use only historically resilient alphas.

5. Unify cost model across selection/backtest/live research.
- Goal: avoid optimizing to one cost proxy and reporting another.

## 6. PIT Safety / Look-Ahead Risks In Proposed Changes

1. Regime-conditional alpha selection must use only regime labels/IC stats available before the rebalance date.
- Safe pattern: rolling train-window estimates; apply to next OOS fold only.

2. Expected-net-benefit trade gate must estimate alpha gain from ex-ante signal data only.
- Do not use realized same-day or future returns when deciding whether to trade.

3. Dynamic universe must remain point-in-time.
- Liquidity filters must use lagged ADV / status / sector data available at rebalance time.

4. Capacity-aware cost model must avoid future liquidity leakage.
- ADV, spreads, halt status, foreign room, price-limit assumptions must be timestamped `as_of <= available_at`.

5. Regime tuning should remain nested-CV or walk-forward only.
- `optuna_regime_nested_cv.py` is directionally correct; do not collapse back to full-sample tuning.

## 7. Practical Conclusion

Most likely near-term improvement path:

1. Trade less.
2. Hold more names.
3. Reject high-turnover alphas earlier.
4. Make regime logic control turnover appetite, not just exposure.
5. Optimize on net-of-cost utility, not raw IC or raw weight deltas.

Expected outcome:

- Quick wins should primarily reduce cost drag and left-tail folds.
- Medium-term changes should improve both net Sharpe and drawdown consistency.
- Long-term gains depend on raising gross IC above the current `~0.013` regime; without that, cost work alone can stabilize but not fully solve Sharpe.
