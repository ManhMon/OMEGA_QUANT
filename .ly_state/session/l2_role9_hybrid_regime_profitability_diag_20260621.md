# L2 Report: Hybrid Regime Profitability Diagnosis

**Gate:** `HYBRID_REGIME_PROFITABILITY_DIAG_20260621`
**Role:** 9 (Backend Engineer, Tier 2)
**Platform:** OpenCode
**Date:** 2026-06-21
**Revision:** 2 (L3 remediation — sign reconciliation, alpha_ic_per_regime, tempfile fix, forbidden-path audit)
**Status:** COMPLETE — Instrumentation added, root cause identified, sign mismatch resolved

---

## 1. Provenance

### Agent Definition (repo-local)
- `.agents/agent/backend-engineer.md` — role_id: 9, tier: 2, skills declared: `[nodejs-best-practices, api-patterns, database-design, clean-code, testing-patterns, systematic-debugging]`

### Skills Read (repo-local, REPO_SKILL_ROOT = `.agents/skills/`)
| Skill | Path | Status |
|-------|------|--------|
| nodejs-best-practices | `.agents/skills/nodejs-best-practices/SKILL.md` | READ OK |
| api-patterns | `.agents/skills/api-patterns/SKILL.md` | READ OK |
| database-design | `.agents/skills/database-design/SKILL.md` | READ OK |
| clean-code | `.agents/skills/clean-code/SKILL.md` | READ OK |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | READ OK |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | READ OK |

### Forbidden Path Scan (Revision 2 — explicit coverage)
| Path | Scanned? | Result |
|------|----------|--------|
| `.gemini\antigravity-ide\scratch\ag-kit` | YES | NOT ACCESSED — non-authoritative, not used as source |
| `.openclaw\skills` | YES | NOT ACCESSED — non-authoritative, not used as source |
| `C:\Users\GHC\.agents` | YES | NOT ACCESSED — non-authoritative, not used as source |
| `.codex\memories` | YES | NOT ACCESSED — non-authoritative, not used as source |
| Any non-repo-local skill source | YES | NOT ACCESSED |

**Verdict:** All skill files read exclusively from `REPO_SKILL_ROOT = C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\`. All four forbidden paths above are confirmed NOT present in the repo tree (glob scan returned zero matches for `.gemini/**`, `.openclaw/**`, `.codex/**` under REPO_ROOT) and were NOT used as source material. The external path `C:\Users\GHC\.agents\` exists on disk but was NOT accessed — only `C:\Users\GHC\repos\OMEGA_QUANT\.agents\` was used.

---

## 2. Problem Statement

All 45/45 CPCV folds of the Hybrid GMM-BOCPD regime backtest produce **negative mean net return** (mean = -6.88%, median = -6.24%). This report diagnoses the root cause using instrumentation-only changes (no strategy/risk/overlay logic modified).

---

## 3. Existing Artifact Reuse

Reused CPCV artifacts from `HYBRID_REGIME_FULL_BACKTEST_20260620` + `HYBRID_REGIME_BACKTEST_PERF_20260621`:
- `data/phase35_results/hybrid_regime_cpcv_comparison_full_evidence_20260621_1335.json` (aggregate)
- `data/phase35_results/hybrid_fold{1..45}_Hybrid_full_evidence_20260621_1335.json` (per-fold, includes `cost_breakdown`)
- `data/phase35_results/hybrid_fold{1..45}_Baseline_full_evidence_20260621_1335.json` (per-fold)

All 45 Hybrid per-fold JSONs contain `cost_breakdown` with `total_cost`, `total_turnover`, `total_commission_cost`, `total_spread_cost`, `total_slippage_cost`.

**Verified:** `total_cost == total_commission_cost + total_spread_cost + total_slippage_cost` in ALL 45/45 folds (0 mismatches).

---

## 4. Per-Fold Diagnostic Metrics (AUTHORITATIVE — from JSON artifacts)

### Formula (documented per FIX 3)

```
gross_return (%) = net_return (%) + total_cost (%)

where:
  net_return = total_return * 100  (compound post-cost return from JSON)
  total_cost = cost_breakdown["total_cost"] * 100
             = (total_commission_cost + total_spread_cost + total_slippage_cost) * 100

This is an ADDITIVE APPROXIMATION to true compound gross return.
Source: apply_realistic_tc() in src/omega/quant/execution_sim.py, line 871:
  "total_cost": float(total_commission + total_spread + total_slippage)

Note: Settlement drag, halt drag, and foreign drag are NOT included in
total_cost (they are very small: settlement_drag = 2/252 * 0.0001 ≈ 0 per bar;
halt_drag and foreign_drag are 0 in these artifacts).
```

### Per-Fold Table (AUTHORITATIVE from diag script output)

```
Fold | Net Ret% |      TC% | Gross Ret% |   Turnover | Avg TO/bar | Cost/bar bps | N Days |   MaxDD%
-----+----------+----------+------------+------------+------------+--------------+--------+---------
   1 |    -5.07 |     3.98 |      -1.09 |      12.96 |     0.0237 |       0.7263 |    548 |    -5.07
   2 |    -5.19 |     3.17 |      -2.02 |      10.85 |     0.0130 |       0.3800 |    833 |    -5.19
   3 |   -15.39 |    22.38 |      +6.99 |      53.50 |     0.0479 |       2.0021 |   1118 |   -15.53
   4 |    -6.05 |     6.63 |      +0.58 |      22.52 |     0.0161 |       0.4726 |   1403 |    -6.25
   5 |    -5.38 |     2.72 |      -2.66 |       9.46 |     0.0056 |       0.1612 |   1688 |    -5.38
   6 |    -6.45 |     7.56 |      +1.11 |      25.35 |     0.0128 |       0.3831 |   1973 |    -7.13
   7 |    -5.79 |     4.46 |      -1.33 |      15.34 |     0.0068 |       0.1975 |   2258 |    -5.79
   8 |    -7.56 |     7.19 |      -0.37 |      23.63 |     0.0093 |       0.2828 |   2543 |    -7.56
   9 |    -5.93 |     5.37 |      -0.56 |      18.17 |     0.0064 |       0.1891 |   2837 |    -5.93
  10 |   -12.12 |    16.57 |      +4.45 |      40.88 |     0.0717 |       2.9064 |    570 |   -12.40
  11 |    -9.10 |    12.21 |      +3.11 |      32.65 |     0.0382 |       1.4275 |    855 |    -9.59
  12 |    -7.92 |     9.24 |      +1.32 |      28.62 |     0.0251 |       0.8105 |   1140 |    -7.93
  13 |   -12.38 |    17.34 |      +4.96 |      45.62 |     0.0320 |       1.2169 |   1425 |   -12.86
  14 |    -8.16 |    10.48 |      +2.32 |      30.03 |     0.0176 |       0.6130 |   1710 |    -8.44
  15 |    -7.47 |     9.66 |      +2.18 |      29.78 |     0.0149 |       0.4840 |   1995 |    -8.75
  16 |    -2.74 |     7.89 |      +5.15 |      23.53 |     0.0103 |       0.3461 |   2280 |    -6.64
  17 |    -3.06 |     6.61 |      +3.56 |      21.16 |     0.0082 |       0.2569 |   2574 |    -6.32
  18 |    -5.72 |     7.60 |      +1.88 |      27.14 |     0.0476 |       1.3328 |    570 |    -6.66
  19 |    -6.73 |     8.64 |      +1.92 |      30.54 |     0.0357 |       1.0109 |    855 |    -7.20
  20 |    -5.61 |     9.49 |      +3.88 |      34.66 |     0.0304 |       0.8323 |   1140 |    -6.52
  21 |    -7.31 |     9.14 |      +1.83 |      32.65 |     0.0229 |       0.6416 |   1425 |    -7.49
  22 |    -5.12 |     7.73 |      +2.61 |      27.98 |     0.0164 |       0.4520 |   1710 |    -6.59
  23 |    -4.99 |     8.28 |      +3.29 |      28.11 |     0.0141 |       0.4152 |   1995 |    -7.14
  24 |    -6.40 |     8.98 |      +2.58 |      32.11 |     0.0140 |       0.3925 |   2289 |    -7.08
  25 |    -7.39 |    11.22 |      +3.82 |      42.82 |     0.0751 |       1.9678 |    570 |    -7.71
  26 |    -8.34 |    15.65 |      +7.31 |      57.53 |     0.0673 |       1.8304 |    855 |    -9.01
  27 |    -5.29 |     2.81 |      -2.48 |       9.63 |     0.0085 |       0.2466 |   1140 |    -5.31
  28 |    -6.24 |     6.89 |      +0.66 |      26.34 |     0.0185 |       0.4838 |   1425 |    -6.66
  29 |    -5.63 |     4.00 |      -1.63 |      15.28 |     0.0089 |       0.2337 |   1710 |    -6.17
  30 |    -5.99 |     4.84 |      -1.15 |      19.00 |     0.0095 |       0.2415 |   2004 |    -6.23
  31 |    -7.88 |     9.52 |      +1.65 |      34.66 |     0.0608 |       1.6711 |    570 |    -8.08
  32 |    -8.73 |    11.26 |      +2.53 |      38.58 |     0.0451 |       1.3165 |    855 |    -8.77
  33 |    -7.83 |     8.74 |      +0.91 |      32.26 |     0.0283 |       0.7666 |   1140 |    -8.05
  34 |    -8.99 |    10.25 |      +1.27 |      35.91 |     0.0252 |       0.7195 |   1425 |    -9.12
  35 |    -8.67 |     9.66 |      +0.99 |      34.70 |     0.0202 |       0.5620 |   1719 |    -8.89
  36 |    -7.85 |    11.98 |      +4.13 |      49.99 |     0.0877 |       2.1016 |    570 |    -7.96
  37 |    -6.00 |     6.81 |      +0.81 |      28.95 |     0.0339 |       0.7961 |    855 |    -6.03
  38 |    -8.61 |    11.36 |      +2.74 |      46.05 |     0.0404 |       0.9964 |   1140 |    -8.73
  39 |    -7.11 |    10.44 |      +3.33 |      43.93 |     0.0306 |       0.7278 |   1434 |    -7.19
  40 |    -4.50 |     6.51 |      +2.02 |      29.05 |     0.0510 |       1.1426 |    570 |    -6.28
  41 |    -6.22 |     8.79 |      +2.57 |      38.59 |     0.0451 |       1.0280 |    855 |    -7.23
  42 |    -4.58 |     5.43 |      +0.85 |      24.26 |     0.0211 |       0.4730 |   1149 |    -5.94
  43 |    -4.89 |     7.68 |      +2.79 |      33.47 |     0.0587 |       1.3473 |    570 |    -4.89
  44 |    -5.19 |     2.81 |      -2.38 |      12.34 |     0.0143 |       0.3256 |    864 |    -5.19
  45 |    -6.02 |    14.08 |      +8.06 |      61.93 |     0.1070 |       2.4315 |    579 |    -7.52
```

### Aggregate Statistics (AUTHORITATIVE)

```
         | Net Ret% |   TC%  | Gross Ret% | Turnover
---------+----------+--------+------------+----------
Mean     |   -6.88  |   8.76 |    +1.88   |   30.50
Median   |   -6.24  |   8.64 |    +1.92   |   29.78
Min      |  -15.39  |   2.72 |    -2.66   |    9.46
Max      |   -2.74  |  22.38 |    +8.06   |   61.93
```

### Cost Breakdown Composition (mean across 45 folds)

```
Commission: mean=6.10%  (range 1.89 - 12.39)  — 69.6% of TC
Spread:     mean=0.61%  (range 0.19 -  1.24)  —  7.0% of TC
Slippage:   mean=2.05%  (range 0.10 - 10.61)  — 23.4% of TC
TOTAL:      mean=8.76%
```

---

## 5. Sign Mismatch Resolution (FIX 3 — Root Cause Verdict)

### Issue
- L2 Report Rev 1, Section 4 table claimed mean gross = **-1.88%**
- L2 Report Rev 1, Section 5 text claimed mean gross = **+1.88%**

### Root Cause
The Rev 1 Section 4 per-fold table contained **incorrect TC% values** (transcription error by the previous agent run). For example:
- Fold 3: table said TC=10.57%, actual JSON shows TC=22.38%
- Fold 10: table said TC=9.01%, actual JSON shows TC=16.57%
- Fold 26: table said TC=6.23%, actual JSON shows TC=15.65%

The incorrect TC values (mean 5.00% instead of 8.76%) produced an incorrect mean gross of -1.88%.

### Verdict
- **The AUTHORITATIVE mean gross return is +1.88%** (computed from actual JSON artifacts, verified by diag script).
- **35/45 folds (77.8%) have POSITIVE gross return** — the alpha signal is real.
- **ALL 35/35 positive-gross folds have TC > gross** — transaction costs consume 100%+ of the alpha.
- The formula `gross = net + total_cost` is correct. `total_cost = commission + spread + slippage` (verified: 0/45 mismatches in JSON artifacts).
- The previous Rev 1 Section 5 analysis was **CORRECT**; the Section 4 table was **INCORRECT**.

---

## 6. Root Cause Hypothesis Verdicts

### (a) TC Exceeds Gross Alpha — **CONFIRMED**
- 35/45 folds (77.8%) have positive gross return (mean +1.88%)
- **ALL 35 of those folds have TC > gross** (100% of positive-gross folds)
- Mean TC = 8.76% vs mean gross = +1.88% → net = -6.88%
- **Verdict:** Transaction costs consume 100%+ of gross alpha across all folds where alpha exists. This is the PRIMARY root cause.

### (b) Regime Filter Over-Blocks (Cash Days High in Bull) — **INCONCLUSIVE**
- 45/45 folds (100%) end with `final_w` all zeros (portfolio in cash/cooldown)
- However, the average `avg_turnover_per_bar` = 0.031 is low, suggesting the portfolio IS trading during most of the period
- The GMM regime dampening (bear_dampening=0.3, sideways_scale=0.8) reduces exposure but does not fully block it
- **Verdict:** The drawdown control (not the regime filter) is the primary driver of end-of-fold cash. Regime dampening contributes by reducing gross alpha below TC threshold.

### (c) Alpha Edge Too Weak — **CONFIRMED**
- Mean gross return = +1.88% over ~1327 trading days (~5.3 years)
- This is ~0.36% annualized gross alpha — far too small to cover even reduced TC
- Baseline gross = +31.97% (same period, no regime dampening) — showing the raw signal has ~6% annualized alpha
- Hybrid regime dampening reduces gross alpha by 30.09 percentage points vs Baseline
- **Verdict:** The composite alpha signal has marginal edge. The Hybrid regime overlay suppresses ~94% of the raw Baseline alpha (1.88% vs 31.97%), leaving too little to cover TC.

### (d) Drawdown Control Cash Drag During Recovery — **CONFIRMED**
- 45/45 folds (100%) end in cash (final_w all zeros)
- DrawdownControlOverlay with threshold=-5%, cooldown=5d, adaptive_re_entry, BOCPD, GMM bull reentry filter
- The max_global_dd floor at -9% blocks re-entry when cumulative DD is too deep
- **Verdict:** Drawdown control correctly protects capital (Hybrid MaxDD mean -7.48% vs Baseline -24.18%) but the frequent stop-outs + extended cooldowns create persistent cash drag that compounds losses.

### (e) Other — **COMMISSION IS DOMINANT COST**
- Commission: mean 6.10% (69.6% of total TC)
- Spread: mean 0.61% (7.0% of total TC)
- Slippage: mean 2.05% (23.4% of total TC)
- The 15bps buy + 15bps sell + 10bps tax_sell commission structure is the dominant cost driver
- **Verdict:** Commission costs alone (6.10%) exceed the entire gross alpha (1.88%) by 3.2x.

---

## 7. Hybrid vs Baseline Comparison

```
Metric          | Baseline    | Hybrid      | Delta (Hybrid - Baseline)
----------------+-------------+-------------+------------------------
Mean Net Return |  -23.69%    |   -6.88%    |  +16.81% (Hybrid BETTER)
Mean TC         |   55.66%    |    8.76%    |  -46.90% (Hybrid BETTER)
Mean Gross Ret  |  +31.97%    |   +1.88%    |  -30.09% (Hybrid WORSE)
Mean Turnover   |  128.3      |   30.5      |   -97.8  (Hybrid LOWER)
Mean MaxDD      |  -24.18%    |   -7.48%    |  +16.70% (Hybrid BETTER)
```

**Key insight:** The Hybrid regime overlay achieves its primary goal — reducing MaxDD from -24.18% to -7.48% (a 16.7 percentage-point improvement). It also reduces TC by 84% (55.66% → 8.76%) through 4x lower turnover. However, it suppresses gross alpha by 94% (31.97% → 1.88%), leaving too little alpha to cover even the reduced TC.

---

## 8. Alpha IC Per Regime (NEW — FIX 1)

### Instrumentation Added
`alpha_ic_per_regime` computes the Pearson correlation between `composite_signal[t]` and `returns[t+1]` (next-day), segmented by GMM regime label (Bull/Sideways/Bear).

- Per-fold: computed in `compute_fold_profitability_diagnostics()` using `gmm_model.predict_regime()` on the date-level mean of latent AE features.
- Cross-sectional IC per date, then averaged within each regime group.
- Aggregated across folds in `aggregate_fold_results()`.
- Emitted into per-fold JSON and aggregate comparison output.

**Note:** alpha_ic_per_regime requires a re-run of the full backtest to populate (existing JSON artifacts pre-date this instrumentation). The instrumentation is in place and will emit on next backtest run.

---

## 9. Instrumentation Changes

### Files Modified (Revision 2)

| File | Change Type | Description |
|------|------------|-------------|
| `scripts/backtest_hybrid_regime.py` | MODIFY fn | `compute_fold_profitability_diagnostics()` — added `gmm_model` param, `alpha_ic_per_regime`, formula docstring, fwd-return shift |
| `scripts/backtest_hybrid_regime.py` | MODIFY class | `DiagnosticBacktestOutputHandler` — added `gmm_model` param, passes to diag function |
| `scripts/backtest_hybrid_regime.py` | MODIFY fn | `run_single_fold()` — passes `gmm_model` to diagnostic handler |
| `scripts/backtest_hybrid_regime.py` | MODIFY fn | `aggregate_fold_results()` — aggregates `alpha_ic_per_regime` (bull/sideways/bear) |
| `scripts/backtest_hybrid_regime.py` | MODIFY fn | `print_comparison_table()` — prints per-regime IC summary table |
| `scripts/backtest_hybrid_regime.py` | MODIFY import | Added `Any` to typing import |
| `scripts/diag_profitability.py` | MODIFY | Added formula docstring, dynamic fold count, formula verification section, alpha_ic_per_regime output section |
| `tests/phase35/test_hybrid_regime_backtest_perf.py` | MODIFY | `test_diagnostic_handler_wraps_correctly` — replaced `tempfile.TemporaryDirectory()` with pytest `tmp_path` fixture (FIX 2) |
| `tests/phase35/test_hybrid_regime_backtest_perf.py` | MODIFY | `test_aggregate_includes_diagnostics` — added `alpha_ic_per_regime` verification |
| `tests/phase35/test_hybrid_regime_backtest_perf.py` | ADD tests | `test_alpha_ic_per_regime_emitted` — verifies new metric is emitted |
| `tests/phase35/test_hybrid_regime_backtest_perf.py` | ADD tests | `test_gross_return_formula_documented` — verifies formula consistency |

### Files Read-Only (No Changes)
| File | Purpose |
|------|---------|
| `src/omega/quant/pipeline_v2.py` | Hot path for cost breakdown — read-only |
| `src/omega/quant/pipeline/overlays/drawdown_control.py` | Cash/cooldown extraction — read-only |
| `src/omega/quant/portfolio/execution_sim.py` | Cost model — read-only (verified formula on line 871) |
| `src/omega/quant/execution_sim.py` | VNCostModel, apply_realistic_tc — read-only |
| `src/omega/quant/strategy/latent_gmm.py` | LatentGMMRegime.predict_regime() — read-only |

### Diagnostic Metrics Emitted Per-Fold
1. `gross_return` — return pre-transaction-cost (compound net + total_cost, additive approx)
2. `total_tc_pct` — sum(commission + spread + slippage) as fraction
3. `cash_days_pct` — fraction of days where sum(|w|) < 0.05
4. `turnover_avg` — mean daily |w_t - w_{t-1}|.sum()
5. `exposure_avg` — mean sum(|w|)
6. `alpha_ic_overall` — cross-sectional IC (signal vs next-day return, averaged across dates)
7. `alpha_ic_per_regime` — IC segmented by GMM regime (bull/sideways/bear)

---

## 10. Test Results

```
tests/phase35/test_hybrid_regime_backtest_perf.py — 30 passed, 0 failed
  TestPrecomputeAlphaLags:           4 passed (existing)
  TestTrainFoldModelsCompositeSignal: 3 passed (existing)
  TestRunSingleFoldSignature:         1 passed (existing)
  TestMainHasWorkersArg:              1 passed (existing)
  TestVectorizedQueryDynamic:         1 passed (existing)
  TestParallelFoldOrderingDeterminism:3 passed (existing)
  TestPITLeakRegression:             4 passed (existing)
  TestProfitabilityDiagnostics:       9 passed (7 existing + 2 NEW)
  TestExistingArtifactDiagnostics:    4 passed (existing)
```

### PRESERVED Invariants
- PIT safety: no overlay logic changed
- No regression on approved DD remediation gate (`HYBRID_REGIME_DD_REMEDIATION_20260621`)
- All existing tests continue to pass
- tempfile Windows ACL issue resolved (FIX 2)

---

## 11. Summary & Recommendations

### Root Cause (Ranked by Impact)

1. **PRIMARY: TC exceeds gross alpha** — Commission costs (6.10% mean) alone exceed the Hybrid gross alpha (1.88% mean) by 3.2x. The alpha signal is real (35/45 folds positive gross) but TC consumes 100% of it.

2. **SECONDARY: Weak alpha edge** — The composite signal produces ~0.36% annualized gross alpha in Hybrid mode, insufficient to cover even optimally-reduced TC.

3. **TERTIARY: Drawdown control cash drag** — 100% of folds end in cash due to stop-out/cooldown cycles. While this correctly limits MaxDD (-7.48% vs -24.18%), the frequent re-entry blocks compound opportunity cost.

### Actionable Recommendations (for Tier 3 / Strategy roles)

1. **Reduce commission rates** — Negotiate lower broker fees or use limit orders. Current 15bps buy + 15bps sell + 10bps tax = 40bps round-trip is prohibitive for this alpha magnitude.

2. **Relax regime dampening** — Increase `latent_gmm_bear_dampening` from 0.3 to 0.5-0.7, `sideways_scale` from 0.8 to 0.9. This would recover some gross alpha while still providing DD protection.

3. **Increase signal strength** — The Ridge-blended composite signal has ~6% annualized raw alpha (Baseline gross). More alpha features or better blending weights could increase Hybrid gross above the TC floor.

4. **Reduce rebalance frequency further** — Current weekly rebalance with EMA smoothing (alpha=0.10) still generates ~30x cumulative turnover. Monthly rebalance or higher EMA alpha could cut TC further.

---

## 12. Tier 3 Audit Submission

Submitting to:
- Code Reviewer (role 21): Code quality review of instrumentation
- QA Engineer (role 17): Test coverage verification (30/30 passing)
- Security Auditor (role 18): No security-relevant changes (instrumentation only)
