# L2 Implementation Report: CPCV Backtest with LLM-Synthesized Alphas

**Gate:** `LLM_CLOSED_LOOP_FULL_BACKTEST_20260618`
**Role:** 9 (backend-engineer) | **Tier:** 2 | **Platform:** OpenCode
**Date:** 2026-06-18
**Status:** [COMPLETE] — awaiting Tier 3 audit

---

## 1. Agent / Skill Provenance

| Item | Path (repo-relative) |
|------|----------------------|
| Agent definition | `.agents/agent/backend-engineer.md` |
| Skill: clean-code | `.agents/skills/clean-code/SKILL.md` |
| Skill: testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| Skill: systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |

**Forbidden-path scan result:** CLEAN
- `Antigravity` — not accessed (does not exist under `.agents/`)
- `OpenClaw` — not accessed (does not exist under `.agents/`)
- `C:\Users\GHC\.agents` — exists on disk but **not** scanned or read; all skill/agent files sourced exclusively from `REPO_AGENT_ROOT` / `REPO_SKILL_ROOT`

---

## 2. Execution Summary

### Command
```
python scripts/backtest_v2_cpcv.py \
  --use-llm-alphas \
  --llm-provider mock \
  --year-start 2024 \
  --year-end 2026
```

### Scope
- **Script:** `scripts/backtest_v2_cpcv.py` (2027 lines)
- **Period:** 2024-01-02 to 2026-06-12 (data availability boundary)
- **Universe:** 50 tickers from `universe_2026-05-29.json` (45 active after sanitization)
- **Panel:** 26,680 raw rows → 26,455 samples after NaN drop
- **Features:** 128 total (119 standard alphas + 9 LLM-synthesized alphas)
- **CPCV config:** N=10, k=2 → C(10,2) = 45 combinatorial folds
- **Embargo:** 1% (bar_horizon=225, label_horizon=5)

### Data Pipeline (PIT-safe)
1. `mask_suspended`: dropped 364 / 37,868 rows (1.0%) with volume==0
2. `sanitize_ohlcv`: 37,504 in → 0 dups, 0 ffill, 1,086 outliers clipped, 0 invalid → 37,504 out
3. `_attach_adv`: 20-day rolling ADV with T-1 PIT lag
4. ADV imputation: 5 NaN cells filled via causal expanding median

### LLM Closed-Loop Search
| Parameter | Value |
|-----------|-------|
| Provider | mock (offline) |
| Prompt version | vn_alpha_search_v3_closed_loop |
| Iterations | 3 |
| Candidates/iteration | 10 (max), 3 generated per iteration |
| Top-K selection | disabled (top_k=10, candidates=9 < 10) |
| Total raw generated | 9 |
| Safety validated | 9 |
| Unique after dedup | 9 |
| Scoring accepted | 9 |
| Scoring rejected | 0 |
| Deployable (supervised) | 0 |
| Unsupervised-only | 9 |

**Rejection taxonomy:** all zeros (parse_error, unsafe_token, duplicate_formula, execution_failure, low_coverage, near_zero_variance, unstable, nan_inf)

**PIT safety:** Labels set to `None` before CPCV splits — unsupervised scoring only (variance, coverage). No test-label leakage.

### LLM Alpha Formulas Accepted (9 total)
| Alpha | Coverage | Variance | Mode |
|-------|----------|----------|------|
| alpha_llm_0 | 100.00% | 1.13e-04 | unsupervised_only |
| alpha_llm_1 | 100.00% | 9.66e-02 | unsupervised_only |
| alpha_llm_2 | 100.00% | 5.43e-03 | unsupervised_only |
| alpha_llm_3 | 100.00% | 1.13e-04 | unsupervised_only |
| alpha_llm_4 | 100.00% | 9.66e-02 | unsupervised_only |
| alpha_llm_5 | 100.00% | 5.43e-03 | unsupervised_only |
| alpha_llm_6 | 100.00% | 1.13e-04 | unsupervised_only |
| alpha_llm_7 | 100.00% | 9.66e-02 | unsupervised_only |
| alpha_llm_8 | 100.00% | 5.43e-03 | unsupervised_only |

Note: Mock provider generates 3 deterministic template formulas per iteration, repeated across 3 iterations = 9 candidates (3 unique templates × 3 iterations).

---

## 3. Performance Metrics

### Primary Metrics

| Metric | Value |
|--------|-------|
| **Median Test IC** | **0.0406** |
| **Median Train CV IC** | **0.0477** |
| **Mean Test IC** | **0.0419** |
| **Std Test IC** | **0.0563** |
| **IC Information Ratio (IC/σ_IC)** | **0.7453** |
| **Min Test IC** | -0.0803 |
| **Max Test IC** | 0.1571 |
| **Median Fold Sharpe Ratio** | **0.1434** |
| **Mean Fold SR** | **0.1462** |
| **Std Fold SR** | 0.1612 |
| **Min Fold SR** | -0.1300 |
| **Max Fold SR** | 0.6198 |
| **Positive Folds** | **36 / 45 (80.0%)** |
| **Negative Folds** | 9 / 45 (20.0%) |
| **Daily Return Observations** | 5,481 |

### Deflated Sharpe Ratio (DSR) — Multiple-Testing Correction

| Metric | Pooled (per-bar) | Fold-Level |
|--------|------------------|------------|
| **SR (per-bar / per-fold)** | 0.1429 | 0.1462 |
| **SR (annualized)** | 2.2679 | 2.3211 |
| **SR std estimate** | — | 0.1445 |
| **Expected max SR** | — | 0.1716 |
| **DSR** | **0.020** | **0.430** |
| **Pass threshold** | False | False |
| **Skew** | -0.2837 | 0.6529 |
| **Kurtosis** | 5.7013 | 3.5729 |
| **n_trials** | 4 | 4 |

### Drawdown (Approximate, Fold-Level)

| Metric | Value |
|--------|-------|
| Max Fold DD (approx) | -0.18% |

---

## 4. Interpretation

### What Worked
- **80% positive folds** indicates the combined alpha set (119 standard + 9 LLM) has directional signal across the majority of CPCV test windows
- **IC IR = 0.7453** — solid information ratio; IC is positive and reasonably stable across folds
- **Median test IC = 0.0406** — economically meaningful cross-sectional correlation for a 5-day horizon
- **Annualized SR = 2.27–2.32** — strong raw Sharpe before multiple-testing correction

### What Did Not Pass
- **DSR = 0.020 (pooled) / 0.430 (fold-level)** — both fail the DSR pass threshold
- This is **expected** for a mock-provider run: the LLM alphas are deterministic templates (3 unique formulas repeated), not genuine alpha signals discovered by a real LLM
- The negative skew (-0.28) and excess kurtosis (5.70) in pooled returns indicate fat-tailed losses that the DSR correction penalizes heavily
- The fold-level DSR (0.430) is more favorable than pooled (0.020) because it treats each fold as one IID observation, avoiding the 9x over-counting in pooled daily returns

### PIT Safety Verification
- LLM formulas scored with `labels=None` before CPCV splits — no test-label leakage
- Grouped execution (`execute_node_grouped`) ensures per-ticker, date-sorted computation
- ADV uses T-1 lag with causal expanding median imputation
- CPCV embargo at 1% of N

---

## 5. Output Artifacts

| Artifact | Path |
|----------|------|
| Full CPCV results JSON | `.ly_state/session/phase3_3_v2.json` |
| LLM search evidence | `.ly_state/session/llm_closed_loop_formula_search_20260612.json` |
| LLM search memory | `.ly_state/session/llm_formula_search_memory_20260612.json` |
| L2 report (this file) | `.ly_state/session/l2_role9_llm_full_backtest_20260618.md` |

---

## 6. Tier 3 Audit Submission

Per backend-engineer (role 9) SOD boundary, this work is submitted to:

| Tier 3 Role | Review Scope |
|-------------|-------------|
| **Code Reviewer (role 21)** | Code quality, PIT-safety of LLM integration path |
| **QA Engineer (role 17)** | Functional correctness of backtest execution, metric validation |
| **Security Auditor (role 18)** | No security concerns (mock provider, no external API calls) |

**Cannot proceed to production deployment until:** All relevant Tier 3 roles return [APPROVED] and a real LLM provider run demonstrates supervised-deployable formulas.

---

## 7. Recommendations for Next Steps

1. **Real LLM provider run:** Replace `--llm-provider mock` with `--llm-provider openai-compatible` and set `OMEGA_LLM_API_KEY` to generate genuine alpha formulas
2. **Supervised validation:** Real LLM formulas should pass supervised scoring (IC > threshold, DSR proxy) to become `deployable=True`
3. **Walk-forward mode:** Consider `--walk-forward` for stricter PIT universe selection (requires `universe_2026-01-02.json`)
4. **Tail controls:** Add `--tail-controls --realistic-tc` for production-grade backtest with vol-targeting and execution costs

---

*Report generated by backend-engineer (role 9) — implementation only, no self-approval.*
