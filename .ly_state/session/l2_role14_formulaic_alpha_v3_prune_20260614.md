# L2 Implementation Report — Formulaic Alpha V3 Prune/Ablation

**Gate:** `FORMULAIC_ALPHA_V3_PRUNE_20260614`
**Role:** 14 — Data Scientist (L2 Implementation)
**Date:** 2026-06-14
**Status:** Implementation Complete — Awaiting Tier 3 Audit

---

## 1. Objective

Implement Formulaic Alpha v3 prune/ablation set as a research-only opt-in.
V2 was approved but still weak (CPCV12 Avg Portfolio IC 0.0037, Raw IC 0.0083).
V3 prunes negative-IC and weak candidates, retaining only the 5 strongest
positive-IC candidates from v2 CPCV12 evidence.

## 2. V3 Candidate List

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

## 3. Exclusion Rationale

- **alpha_fml089_amihud_illiq_20**: IC -0.0610, strongly negative. Harmful to portfolio.
  No transformation evidence to rehabilitate.
- **alpha_fml078_range_compression_10**: IC -0.0100, anti-predictive in VN market.
  No transformation evidence to rehabilitate.
- **alpha_fml033_vol_vol_interact_10**: IC ~0.0037, at portfolio average.
  Adds noise without improving mean IC. Pruned for parsimony.
- **alpha_fml001_ts_rank_momentum_20**: Already excluded in v2 (negative IC).

## 4. Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/alpha/formulaic_alphas.py` | Added GATE_ID_V3, v3_pruned registry entry, get_v3_ablation_report() |
| `scripts/run_phase35_backtest.py` | Added 'v3_pruned' to --formulaic-alpha-set choices |
| `tests/phase35/test_formulaic_alpha_adapter.py` | Added 30+ v3 test cases; updated v2 choice tests |
| `data/phase35_results/formulaic_v3_ablation_report.json` | Generated ablation report |

## 5. Defaults Unchanged

- `DEFAULT_FORMULAIC_ALPHA_SET` = "small" (unchanged)
- CLI `--formulaic-alpha-set` default = "small" (unchanged)
- No live/default behavior change. V3 is research-only opt-in.

## 6. PIT Safety

- All v3 alphas use existing compute functions (fml052, fml012, fml045, fml067, fml006)
- All verified PIT-safe with T-1 shift per ticker
- No negative shifts in source code
- All outputs sanitized (no inf/nan)

## 7. Tests

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

## 8. Ablation Report

See `data/phase35_results/formulaic_v3_ablation_report.json` for full JSON.
Programmatic access: `from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report`

## 9. Tier 3 Audit Submission

Submitted to:
- Code Reviewer (role 21): Code quality and reproducibility
- QA Engineer (role 17): Model validation and testing review

## 10. Forbidden Path Scan

- `.gemini/antigravity-ide/scratch/ag-kit`: NOT FOUND in repo (clean)
- `.openclaw/skills`: NOT FOUND in repo (clean)
- `C:\Users\GHC\.agents`: NOT SCANNED (outside repo boundary)
- `.codex/memories`: NOT FOUND in repo (clean)

No forbidden paths accessed. All source files are repo-local authoritative.

## 11. Skill Files Read (Authoritative Repo-Local)

1. `.agents/agent/data-scientist.md` — frontmatter parsed
2. `.agents/skills/python-patterns/SKILL.md`
3. `.agents/skills/clean-code/SKILL.md`
4. `.agents/skills/testing-patterns/SKILL.md`
5. `.agents/skills/systematic-debugging/SKILL.md`
6. `.agents/skills/performance-profiling/SKILL.md`
7. `.agents/skills/quant-research/SKILL.md`
8. `.agents/skills/vietnam-market-data/SKILL.md`
9. `.agents/skills/backtesting-pit-safety/SKILL.md`
10. `.agents/skills/data-science-workflow/SKILL.md`
