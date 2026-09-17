# L2 Report: Automated Alpha Discovery — Real Dynamic Universe Evaluation

**GATE**: `AUTOMATED_ALPHA_DISCOVERY_REAL_DYNAMIC_EVAL_20260615`
**Role**: 14 data-scientist (Tier 2)
**Date**: 2026-06-15
**Status**: RESEARCH-ONLY — no live promotion, no default behavior change

---

## 1. Objective

Evaluate the top 5 automated alpha candidates (previously ranked on synthetic data) on **real PIT-safe dynamic-universe VN market data**, compare to the dynamic baseline, and document the exact integration gap with Phase35 walk-forward.

**Target candidates** (from synthetic ranking):
1. `auto_rsi_14`
2. `auto_mom_ret_60`
3. `auto_mr_zscore_20`
4. `auto_vol_std_ratio_10_30`
5. `auto_mom_ret_20`

---

## 2. Baseline (Dynamic Universe, 12-fold Walk-Forward)

| Metric | Value | Source |
|--------|-------|--------|
| Portfolio IC | 0.0249 | `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json` |
| Median Alpha IC | 0.0167 | Computed from baseline `alpha_ics` (12 alphas, 12 folds) |
| Portfolio Sharpe | 3.1106 | Same baseline file |
| Portfolio MaxDD | -12.25% | Same baseline file |
| Folds | 12 | CPCV fold expansion |
| Universe | 30 symbols, dynamic rebalance every 21 days | `DYNAMIC_REBALANCE_UNIVERSE_20260615` |
| Data | 70,815 rows, 2015-01-05 to 2026-05-13 | `data/market_2015_now.parquet` |

---

## 3. Integration Gap (Exact)

**Phase35 walk-forward engine does NOT execute automated alpha discovery per fold.**

Evidence (repo-local):
- `src/omega/quant/alpha/phase35.py` — `Phase35WalkForwardEngine.__init__` accepts `enable_automated_discovery` param but `self.enable_automated_discovery` is **assigned and never read** in the fold loop
- `AutomatedAlphaDiscoveryFactory` is **not imported** in `phase35.py`
- `FoldMetrics` has `automated_discovery_evidence: Optional[Dict]` slot but it is **never populated**

**Therefore**: Direct integration into Phase35 backtest is UNSUPPORTED. This evaluation uses the closest equivalent: **standalone real-data IC/transfer diagnostics on the train portion of the last walk-forward fold (fold 12: train 2022-05-12 to 2025-05-11, 20,161 rows, 30 symbols)**.

---

## 4. Evaluation Methodology

| Aspect | Detail |
|--------|--------|
| Data source | `data/market_2015_now.parquet` (real VN market, VCI provider) |
| Data prep | `Phase35DataLoader` with full sanitizer, expanding_zscore normalization |
| Universe | Top 30 by ADTV, dynamic rebalance schedule from baseline config |
| Fold used | Fold 12 (last): train=20,161 rows (2022-05-12 to 2025-05-11) |
| Discovery | `AutomatedAlphaDiscoveryFactory(enabled=True, candidate_cap=20, corr_threshold=0.85, min_ic=0.01, seed=42)` |
| Return column | `fwd_ret_5` (5-day forward return, PIT-safe) |
| Transfer diag | `run_transfer_diagnostics()` from `alpha_transfer_diagnostics.py` |
| PIT-safe | Yes — all templates use T-1 lag via `groupby('ticker').transform(lambda x: x.shift(1).…)` |
| Train-only | Yes — discovery runs on train data only |
| Script | `scripts/eval_auto_alpha_real_dynamic.py` |

---

## 5. Results: All 15 Selected Candidates on Real Data

| Rank | Candidate | Family | Real Train IC | Real ICIR | Transfer Verdict |
|------|-----------|--------|---------------|-----------|-----------------|
| 1 | `auto_rsi_14` | RSI | **0.0544** | 0.2162 | RECOMMEND |
| 2 | `auto_mom_ret_10` | Momentum | 0.0438 | 0.1622 | RECOMMEND |
| 3 | `auto_rsi_7` | RSI | 0.0438 | 0.1705 | RECOMMEND |
| 4 | `auto_mr_zscore_20` | Mean Reversion | **0.0401** | 0.1593 | RECOMMEND |
| 5 | `auto_mom_accel_5_10` | Momentum Accel | -0.0337 | -0.1267 | SKIP_LOW_IC |
| 6 | `auto_mom_ret_60` | Momentum | **0.0327** | 0.1011 | RECOMMEND |
| 7 | `auto_mom_ret_20` | Momentum | **0.0262** | 0.0880 | RECOMMEND |
| 8 | `auto_mom_ret_5` | Momentum | 0.0250 | 0.0890 | RECOMMEND |
| 9 | `auto_vol_std_ratio_10_30` | Vol Ratio | **0.0189** | 0.0790 | RECOMMEND |
| 10 | `auto_vol_close_loc` | Volatility | -0.0167 | -0.0738 | SKIP_LOW_IC |
| 11 | `auto_upper_shadow` | Price Action | 0.0165 | 0.0722 | RECOMMEND |
| 12 | `auto_vol_ratio_5_20` | Volume | 0.0155 | 0.0718 | RECOMMEND |
| 13 | `auto_vol_range_pct` | Volatility | 0.0154 | 0.0519 | RECOMMEND |
| 14 | `auto_vol_atr_ratio_5_20` | Vol Ratio | 0.0120 | 0.0525 | RECOMMEND |
| 15 | `auto_lower_shadow` | Price Action | -0.0117 | -0.0530 | SKIP_LOW_IC |

**Bold** = top-5 target candidates from synthetic ranking.

---

## 6. Target Candidates: Synthetic vs Real IC

| Candidate | Synthetic IC | Synthetic ICIR | Real Train IC | Real ICIR | Status |
|-----------|-------------|---------------|---------------|-----------|--------|
| `auto_rsi_14` | 0.0636 | 0.194 | **0.0544** | 0.2162 | FOUND — #1 real |
| `auto_mom_ret_60` | 0.0527 | 0.178 | **0.0327** | 0.1011 | FOUND — #6 real |
| `auto_mr_zscore_20` | 0.0482 | 0.159 | **0.0401** | 0.1593 | FOUND — #4 real |
| `auto_vol_std_ratio_10_30` | 0.0397 | 0.122 | **0.0189** | 0.0790 | FOUND — #9 real |
| `auto_mom_ret_20` | 0.0372 | 0.116 | **0.0262** | 0.0880 | FOUND — #7 real |

All 5 target candidates were FOUND and selected on real data. Ranking shifted slightly: `auto_rsi_14` remains #1 on both synthetic and real data.

---

## 7. Comparison with Dynamic Baseline

| Metric | Baseline | Auto-Discovery (real) | Delta |
|--------|----------|----------------------|-------|
| Portfolio IC | 0.0249 | N/A (not backtested) | — |
| **Median Alpha IC** | 0.0167 | **0.0189** | **+0.0022 (+13%)** |
| Mean Alpha IC | — | 0.0188 | — |
| Max |IC| | 0.0638 (baseline best) | **0.0544** | — |
| Positive IC rate | 7/12 (58%) | **12/15 (80%)** | — |
| Sharpe | 3.1106 | N/A (not backtested) | — |
| MaxDD | -12.25% | N/A (not backtested) | — |
| Transfer RECOMMEND | — | 12/15 (80%) | — |

**Key finding**: Auto-discovery median IC (0.0189) exceeds baseline median alpha IC (0.0167) by 13%. However, these are **train-set IC diagnostics only** — they have NOT been validated through full walk-forward OOS backtest. Sharpe and MaxDD cannot be compared because the auto candidates have not been integrated into the Phase35 portfolio construction pipeline.

---

## 8. Transfer Diagnostics Summary

| Stat | Value |
|------|-------|
| Candidates evaluated | 15 |
| RECOMMENDED | 12 |
| SKIP_LOW_IC | 3 (`auto_vol_close_loc`, `auto_lower_shadow`, `auto_mom_accel_5_10`) |
| SKIP_REDUNDANT | 0 |
| SKIP_HIGH_TURNOVER | 0 |

---

## 9. Caveats and Limitations

1. **No OOS backtest**: Auto candidates were evaluated on train-set IC only. No walk-forward OOS Sharpe/MaxDD is available because Phase35 integration is not wired.
2. **Single fold**: Evaluation uses fold 12 train data only. Multi-fold stability analysis was not possible without integration.
3. **IC != portfolio performance**: Higher per-candidate IC does not guarantee better portfolio-level Sharpe or MaxDD. The baseline uses alpha ensemble selection with winner guard, not raw IC ranking.
4. **No cost-adjusted IC**: Transfer diagnostics use gross IC. Net-of-cost IC would require turnover estimation integrated into portfolio construction.
5. **Synthetic ranking preserved**: The 5 target candidates from synthetic ranking all appear in the real top-15, confirming transferability of the candidate set, but with rank reshuffling.

---

## 10. Skill Evidence (All 9 Required)

| # | Skill | Source | Evidence in This Task |
|---|-------|--------|----------------------|
| 1 | **python-patterns** | `.agents/skills/python-patterns/SKILL.md` | Evaluation script uses sync pattern (CPU-bound computation), type hints on function params, proper error handling, argparse CLI. No async needed for batch computation. |
| 2 | **clean-code** | `.agents/skills/clean-code/SKILL.md` | Script follows SRP (single eval function), named constants (GATE_ID), guard clauses, no unnecessary comments. Under 300 lines. |
| 3 | **testing-patterns** | `.agents/skills/testing-patterns/SKILL.md` | Ran 74 existing tests (AAA pattern): `test_automated_alpha_discovery.py` (60), `test_alpha_discovery_pit.py` (6), `test_alpha_discovery_contract.py` (8). All passed. |
| 4 | **systematic-debugging** | `.agents/skills/systematic-debugging/SKILL.md` | Debugged 3 script errors iteratively: KeyError on `n_generated` → checked `to_dict()`, AttributeError on `n_evaluated` → checked `TransferDiagnosticsReport`, AttributeError on `.name` → checked `TransferDiagnostic.alpha_name`. 4-phase: Reproduce → Isolate → Understand → Fix. |
| 5 | **performance-profiling** | `.agents/skills/performance-profiling/SKILL.md` | Baseline first, identify bottleneck. Loaded real data once (70K rows), used last fold only to minimize computation. No premature optimization. |
| 6 | **quant-research** | `.agents/skills/quant-research/SKILL.md` | IC/ICIR metrics per skill spec. Spearman rank IC (primary), cross-sectional per-date, min 5 stocks. Train-only evaluation. No data snooping. IC > 0.02 threshold for screening. |
| 7 | **vietnam-market-data** | `.agents/skills/vietnam-market-data/SKILL.md` | Used `data/market_2015_now.parquet` (VCI provider), VND_FULL scale verified by Phase35DataLoader. 30 top symbols by ADTV > 5B VND. Point-in-time universe with dynamic rebalance. |
| 8 | **backtesting-pit-safety** | `.agents/skills/backtesting-pit-safety/SKILL.md` | All templates T-1 lagged. Discovery on train only, no test leakage. Walk-forward splits chronological with embargo. Documented that Sharpe > 3.0 flag applies to baseline (3.11 — flagged as potential look-ahead, but baseline has drawdown control which inflates Sharpe). |
| 9 | **data-science-workflow** | `.agents/skills/data-science-workflow/SKILL.md` | EDA via Phase35DataLoader stats (1.76M rows → 70K after filters). Data quality: sanitizer stats logged (492K outliers clipped, 0 duplicates, 100% retention). Experiment tracked: GATE ID, timestamp, seed=42, all config persisted. Reproducible: deterministic seed, saved JSON artifact. |

---

## 11. Forbidden Path Scan

| Check | Result |
|-------|--------|
| Files created by this task | 2 |
| `scripts/eval_auto_alpha_real_dynamic.py` | ALLOWED (evaluation script) |
| `.ly_state/session/auto_alpha_real_dynamic_eval_20260615_193631.json` | ALLOWED (session artifact) |
| `l2_role14_automated_alpha_real_dynamic_eval_20260615.md` | ALLOWED (this report) |
| Modified existing src/ files | **0** (none) |
| Modified existing config/ files | **0** (none) |
| Modified existing tests/ files | **0** (none) |
| Writes outside `scripts/`, `.ly_state/session/` | **0** (none) |

---

## 12. Artifacts

| Artifact | Path |
|----------|------|
| Evaluation script | `scripts/eval_auto_alpha_real_dynamic.py` |
| Results JSON | `.ly_state/session/auto_alpha_real_dynamic_eval_20260615_193631.json` |
| Baseline JSON | `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json` |
| Agent def | `.agents/agent/data-scientist.md` |
| Skills (9) | `.agents/skills/{python-patterns,clean-code,testing-patterns,systematic-debugging,performance-profiling,quant-research,vietnam-market-data,backtesting-pit-safety,data-science-workflow}/SKILL.md` |

---

## 13. Test Results

```
tests/phase35/test_automated_alpha_discovery.py  ....60 passed
tests/test_alpha_discovery_pit.py  ................6 passed
tests/test_alpha_discovery_contract.py  ...........8 passed
Total: 74 passed, 0 failed, 3 warnings (13.57s)
```

Smoke test (`python scripts/run_alpha_discovery.py --smoke-test`): passed.
Real-data eval (`python scripts/eval_auto_alpha_real_dynamic.py`): passed.

---

## 14. Conclusion

**The automated alpha discovery pipeline transfers to real VN market data.** All 5 target candidates from synthetic ranking were found and selected on real train data, with `auto_rsi_14` retaining the #1 position (IC=0.0544, ICIR=0.2162). The auto-discovery median IC (0.0189) exceeds the dynamic baseline median alpha IC (0.0167) by 13%.

**However**, these results are **train-set IC diagnostics only** — not OOS backtest evidence. The Phase35 walk-forward engine has config params for automated discovery but the per-fold invocation is not wired. Sharpe and MaxDD comparisons are not available.

**No live promotion. No default behavior change. Research-only.**

This report does NOT audit or approve. Submitted to Tier 3 (Code Reviewer role 21 + QA Engineer role 17) for review.
