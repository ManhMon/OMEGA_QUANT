# L2 Implementation Fix1 Report — Formulaic Alpha V3 Prune/Ablation

**Gate:** `FORMULAIC_ALPHA_V3_PRUNE_FIX1_20260614`
**Parent Gate:** `FORMULAIC_ALPHA_V3_PRUNE_20260614`
**Role:** 14 — Data Scientist (L2 Implementation)
**Date:** 2026-06-14
**Status:** Report Correction — SOD Wording Fix + V3 Output Evidence Clarification
**Fix Scope:** Report/evidence correction only. No production source or test changes.

---

## 1. Objective (Unchanged from Parent)

Implement Formulaic Alpha v3 prune/ablation set as a research-only opt-in.
V2 was approved but still weak (CPCV12 Avg Portfolio IC 0.0037, Raw IC 0.0083).
V3 prunes negative-IC and weak candidates, retaining only the 5 strongest
positive-IC candidates from v2 CPCV12 evidence.

## 2. V3 Candidate List (Unchanged)

| # | Candidate | CPCV12 IC | Family | V2 | V3 |
|---|-----------|-----------|--------|----|----|
| 1 | alpha_fml052_close_zscore_mr_20 | 0.0164 | mean_reversion | yes | **yes** |
| 2 | alpha_fml012_mean_rev_rank_10 | 0.0104 | mean_reversion | yes | **yes** |
| 3 | alpha_fml045_liq_turnover_5 | 0.0091 | liquidity | yes | **yes** |
| 4 | alpha_fml067_vol_price_diverge_10 | 0.0080 | volume_price | yes | **yes** |
| 5 | alpha_fml006_vp_corr_10 | 0.0059 | volume_price | yes | **yes** |
| 6 | alpha_fml033_vol_vol_interact_10 | ~0.0037 | volatility_volume | yes | EXCLUDED |
| 7 | alpha_fml078_range_compression_10 | -0.0100 | mean_reversion | yes | EXCLUDED |
| 8 | alpha_fml089_amihud_illiq_20 | -0.0610 | liquidity | yes | EXCLUDED |

**V3 expected mean candidate IC: 0.0100** (vs v2 portfolio IC 0.0037)

## 3. Exclusion Rationale (Unchanged)

- **alpha_fml089_amihud_illiq_20**: IC -0.0610, strongly negative. Harmful to portfolio.
  No transformation evidence to rehabilitate.
- **alpha_fml078_range_compression_10**: IC -0.0100, anti-predictive in VN market.
  No transformation evidence to rehabilitate.
- **alpha_fml033_vol_vol_interact_10**: IC ~0.0037, at portfolio average.
  Adds noise without improving mean IC. Pruned for parsimony.
- **alpha_fml001_ts_rank_momentum_20**: Already excluded in v2 (negative IC).

## 4. Files Modified (Unchanged from Parent)

| File | Change |
|------|--------|
| `src/omega/quant/alpha/formulaic_alphas.py` | Added GATE_ID_V3, v3_pruned registry entry, get_v3_ablation_report() |
| `scripts/run_phase35_backtest.py` | Added 'v3_pruned' to --formulaic-alpha-set choices |
| `tests/phase35/test_formulaic_alpha_adapter.py` | Added 30+ v3 test cases; updated v2 choice tests |
| `data/phase35_results/formulaic_v3_ablation_report.json` | Generated ablation report |

## 5. Defaults Unchanged (Unchanged)

- `DEFAULT_FORMULAIC_ALPHA_SET` = "small" (unchanged)
- CLI `--formulaic-alpha-set` default = "small" (unchanged)
- No live/default behavior change. V3 is research-only opt-in.

## 6. PIT Safety (Unchanged)

- All v3 alphas use existing compute functions (fml052, fml012, fml045, fml067, fml006)
- All verified PIT-safe with T-1 shift per ticker
- No negative shifts in source code
- All outputs sanitized (no inf/nan)

## 7. Tests (Unchanged)

**105 tests pass** (including 30+ new v3 tests):
- V3 names: all start with alpha_fml, contain window digits
- V3 excludes: amihud_illiq, range_compression, momentum, vol_vol_interact
- V3 finite outputs: no inf/nan with normal and extreme inputs
- V3 PIT/no lookahead: first rows finite after shift(1)
- V3 CLI choice: v3_pruned registered, default still "small"
- V3 default unchanged: confirmed
- V3 determinism: same input = same output
- V3 ablation report: structure, evidence, JSON serializable
- V3 metadata: coverage, family, gate references

## 8. Ablation Report (Unchanged)

See `data/phase35_results/formulaic_v3_ablation_report.json` for full JSON.
Programmatic access: `from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report`

## 9. Tier 3 Audit Submission (Unchanged)

Submitted to:
- Code Reviewer (role 21): Code quality and reproducibility
- QA Engineer (role 17): Model validation and testing review

---

## 10. Forbidden Path Scan — CORRECTED (SOD-Compliant Wording)

**No authoritative reliance** on any of the following paths. None were read,
parsed, referenced, or used as source for any implementation decision in this
gate or its parent gate.

| Forbidden Path | Status | SOD Declaration |
|----------------|--------|-----------------|
| `.gemini\antigravity-ide\scratch\ag-kit` | Non-authoritative and **not used as source** | No authoritative reliance |
| `.openclaw\skills` | Non-authoritative and **not used as source** | No authoritative reliance |
| `C:\Users\GHC\.agents` | Non-authoritative and **not used as source** | No authoritative reliance |
| `.codex\memories` | Non-authoritative and **not used as source** | No authoritative reliance |

**Correction from parent report:** The parent L2 report
(`l2_role14_formulaic_alpha_v3_prune_20260614.md`, section 10) stated
"NOT FOUND in repo (clean)" for some paths and "NOT SCANNED (outside repo
boundary)" for the external user-home agents path. This wording fails strict
SOD because it does not explicitly declare non-authoritative status and
no-reliance. This fix1 report replaces that section with the exact
SOD-compliant declarations above.

All implementation source files are repo-local authoritative only
(`src/`, `scripts/`, `tests/`, `data/` within `C:\Users\GHC\repos\OMEGA_QUANT`).

---

## 11. V3 Output Evidence — CORRECTED (Smoke vs Full CPCV12)

### 11.1 Inspection of Existing Output

**File inspected:** `data/phase35_results/phase35_backtest_results_cpcv12_formulaic_v3_baseline.json`

**Actual configuration recorded in JSON:**

| Parameter | Value in JSON | Full CPCV12 Required |
|-----------|---------------|----------------------|
| `n_folds` | **2** | 12 |
| `n_folds_executed` | **2** | 12 |
| `train_years` | 1 | 3 |
| `test_years` | 1 | 1 |
| `top_n_symbols` | 1 | 30 |
| `quick_mode` | **true** | false |
| `formulaic_alpha_set` | v3_pruned | v3_pruned |

**Fold count in `fold_details`:** 2 folds only (fold_id 1 and fold_id 2).

### 11.2 Classification

The output tagged `cpcv12_formulaic_v3` is a **2-fold smoke test** only.
It is **NOT** a full CPCV12 validation. Specifically:

- Only 2 of 12 folds were executed
- Quick-mode was enabled (`quick_mode: true`)
- Only 1 symbol was used (`top_n_symbols: 1`)
- Training window was 1 year (not the standard 3 years)
- All portfolio-level metrics are zero (IC=0.0, Sharpe=0.0, MaxDD=0.0, PnL=0.0)

**This output must NOT be cited as full CPCV12 evidence.** The "cpcv12" in the
output tag is a naming artifact from the CPCV fold expansion CLI feature, not a
statement that 12 folds were actually executed.

### 11.3 Per-Fold Alpha IC Evidence (Smoke — 2 folds, 1 symbol)

| Alpha | Fold 1 IC | Fold 2 IC | Mean IC |
|-------|-----------|-----------|---------|
| alpha_fml052_close_zscore_mr_20 | 0.0628 | 0.0472 | 0.0550 |
| alpha_fml012_mean_rev_rank_10 | 0.0681 | -0.0507 | 0.0087 |
| alpha_fml045_liq_turnover_5 | -0.0178 | 0.0677 | 0.0249 |
| alpha_fml067_vol_price_diverge_10 | -0.0648 | -0.0037 | -0.0343 |
| alpha_fml006_vp_corr_10 | -0.1144 | 0.0771 | -0.0186 |

**Note:** These ICs are from 1-symbol smoke runs and are not statistically
representative. They serve only as implementation smoke verification (the
formulaic alphas compute without errors, produce finite outputs, and are wired
into the pipeline correctly).

### 11.4 Full 12-Fold V3 CPCV Run — NOT EXECUTED

**Required command:**
```
python scripts/run_phase35_backtest.py \
    --n-folds 12 --train-years 3 --test-years 1 \
    --enable-formulaic-alphas --formulaic-alpha-set v3_pruned \
    --output-tag cpcv12_formulaic_v3_full
```

**Status: NOT RUN — deferred to L1.**

**Rationale:** A full 12-fold CPCV run with 30 symbols, 3-year training
windows, and 1-year test windows requires processing ~11 years of VN market
data across 12 overlapping fold windows with full Stage 1-6 pipeline per fold.
This is computationally expensive (estimated multi-hour runtime) and is not
feasible within an interactive L2 fix session. The smoke test (section 11.2)
confirms correct implementation wiring. Full CPCV12 validation must be
scheduled and executed by L1 with appropriate compute resources and timeout
budget.

**L1 follow-up action required:** Execute the full 12-fold v3 CPCV run with
the command above and persist results as
`phase35_backtest_results_cpcv12_formulaic_v3_full.json` and
`phase35_backtest_summary_cpcv12_formulaic_v3_full.txt`.

---

## 12. Skill Files Read (Authoritative Repo-Local)

1. `.agents/agent/data-scientist.md` — frontmatter parsed (role_id: 14, tier: 2, sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3")
2. `.agents/skills/python-patterns/SKILL.md`
3. `.agents/skills/clean-code/SKILL.md`
4. `.agents/skills/testing-patterns/SKILL.md`
5. `.agents/skills/systematic-debugging/SKILL.md`
6. `.agents/skills/performance-profiling/SKILL.md`
7. `.agents/skills/quant-research/SKILL.md`
8. `.agents/skills/vietnam-market-data/SKILL.md`
9. `.agents/skills/backtesting-pit-safety/SKILL.md`
10. `.agents/skills/data-science-workflow/SKILL.md`

**SKILL SOURCE CONTRACT:**
- REPO_AGENT_ROOT = `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- REPO_SKILL_ROOT = `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`
- Only repo-local skill files read. No external/global agent directories used.

---

## 13. Files Read for This Fix1 Report

| File | Purpose |
|------|---------|
| `.agents/agent/data-scientist.md` | Agent frontmatter, role definition, SOD boundary |
| `.ly_state/session/l2_role14_formulaic_alpha_v3_prune_20260614.md` | Parent L2 report (corrected by this fix1) |
| `data/phase35_results/phase35_backtest_results_cpcv12_formulaic_v3_baseline.json` | V3 backtest JSON — inspected for fold count |
| `data/phase35_results/phase35_backtest_summary_cpcv12_formulaic_v3_baseline.txt` | V3 backtest summary text |
| `data/phase35_results/formulaic_v3_ablation_report.json` | V3 ablation report JSON (implementation evidence) |
| `scripts/run_phase35_backtest.py` (lines 1-397) | CLI arg definitions, fold expansion logic |

---

## 14. Summary of Corrections

| Issue | Parent Report | Fix1 Correction |
|-------|--------------|-----------------|
| Forbidden path SOD wording | "NOT FOUND / NOT SCANNED" — ambiguous | Explicit: "non-authoritative and not used as source" for all 4 paths |
| V3 output tag `cpcv12_formulaic_v3` | Implied CPCV12 coverage | Explicitly classified as **2-fold smoke only**, NOT full CPCV12 |
| Full 12-fold v3 run | Not addressed | Explicitly deferred to L1 with exact command and rationale |
| No authoritative reliance | Not stated | Explicitly declared in section 10 |

---

## 15. Tier 3 Audit Submission

Submitted to:
- Code Reviewer (role 21): Code quality and reproducibility
- QA Engineer (role 17): Model validation and testing review

**This is a report/evidence correction only. No production source or test files were modified.**
