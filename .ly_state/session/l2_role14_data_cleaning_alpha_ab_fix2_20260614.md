# L2 Data-Cleaning A/B Fix2 Report — DATA_CLEANING_ALPHA_AB_FIX2_20260614

**Date**: 2026-06-14
**Gate**: DATA_CLEANING_ALPHA_AB_FIX2_20260614
**Prior gate**: DATA_CLEANING_ALPHA_AB_FIX1_20260614 (verdict: NEEDS_FIX)
**Role**: 14 (data-scientist) — L2 implementation only
**Verdict**: `RESEARCH_ONLY — DO_NOT_PROMOTE`
**Default behavior**: UNCHANGED
**Fix scope**: Report-only corrections applied directly to scoped validation reports

---

## 0. Provenance and Compliance

### Repo-Local Agent Definition Read

| Type | Repo-Relative Path |
|------|-------------------|
| Role definition (frontmatter parsed) | `.agents/agent/data-scientist.md` |

**Frontmatter**:
- `name`: data-scientist
- `role_id`: 14
- `tier`: 2
- `platform`: OpenCode
- `skills`: [python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow]
- `sod_boundary`: "implementation-only, test required, no self-approval, submit to Tier3"

### All 9 Declared Repo-Local Skill Files Read

| # | Skill Name | Repo-Relative Path |
|---|-----------|-------------------|
| 1 | python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| 2 | clean-code | `.agents/skills/clean-code/SKILL.md` |
| 3 | testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| 4 | systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| 5 | performance-profiling | `.agents/skills/performance-profiling/SKILL.md` |
| 6 | quant-research | `.agents/skills/quant-research/SKILL.md` |
| 7 | vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |
| 8 | backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| 9 | data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |

All 9 skills loaded from authoritative repo-local path `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\`. No skill loaded from any non-authoritative path.

### Scoped Validation Reports Read

| Type | Repo-Relative Path |
|------|-------------------|
| Validation report (clean) | `.ly_state/session/cpcv12_formulaic_v3_clean_stat_validation_report_20260614.md` |
| Validation report (clean+WG) | `.ly_state/session/cpcv12_v3_winner_guard_clean_stat_validation_report_20260614.md` |
| L2 fix1 report | `.ly_state/session/l2_role14_data_cleaning_alpha_ab_fix1_20260614.md` |
| L3 audit report | `.ly_state/session/audit_reports/role21_data_cleaning_alpha_ab_fix1_20260614.md` |

### Forbidden Path Scan (Exact Wording)

no authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

**Path existence check**:
- `.gemini\antigravity-ide\scratch\ag-kit` — does NOT exist on disk
- `.openclaw\skills` — does NOT exist on disk
- `C:\Users\GHC\.agents` — exists on disk but not used as source
- `.codex\memories` — does NOT exist on disk

**Result**: No authoritative reliance on any forbidden path. All source material is repo-local under `REPO_ROOT`.

---

## 1. L3 [NEEDS_FIX] Findings Addressed

The L3 audit report (`.ly_state/session/audit_reports/role21_data_cleaning_alpha_ab_fix1_20260614.md`) returned [NEEDS_FIX] with these findings:

### Finding 1 (BLOCKING) — Stale Artifacts Uncorrected

**Original finding**: Prior report blockers were documented in the fix1 report, but stale scoped artifacts remain uncorrected. The original validation reports still contain `CONDITIONAL_PROMOTE`, stale `All 7 alphas` wording, and `Baseline (no RA, no guard)` labels in the clean+WG report. The fix1 report reads as an addendum but does not update or clearly mark the original validation reports as superseded artifacts.

**Fix applied**: Explicit supersession blocks added at the top of both validation reports, AND inline corrections applied directly to the report text. See Section 2 below for details.

### Finding 2 (BLOCKING) — Incomplete Skill Listing

**Original finding**: L2 fix1 report lists only 3 of 9 declared data-scientist skills (quant-research, data-science-workflow, backtesting-pit-safety). The repo-local loading protocol requires each declared skill to be read or the session to stop with [NEEDS_FIX].

**Fix applied**: All 9 declared skills read from repo-local `.agents/skills/` directory and listed in Section 0 above. No skill omitted.

### Finding 3 (NON-BLOCKING) — Fallback Terminology

**Original finding**: The fix1 report correctly distinguishes alpha-selection fallback from winner-guard fallback, but the stale validation report summary still says `Fallback Frequency | 0.0%` without the winner-guard distinction.

**Fix applied**: Inline clarification notes added to both validation reports Section 4 (Fallback Candidate Frequency) distinguishing alpha-selection fallback (0/12) from winner-guard fallback (4/12 folds 1, 2, 5, 7 for clean+WG; N/A for clean).

---

## 2. Corrections Applied to Scoped Reports

### 2.1 Clean Report (cpcv12_formulaic_v3_clean_stat_validation_report_20260614.md)

| Correction | Location | Detail |
|-----------|----------|--------|
| Supersession block added | Top of report (after title) | 5-point correction block with FIX2 gate reference |
| CONDITIONAL_PROMOTE superseded | Selector-Ready Report section | Inline note: superseded by RESEARCH_ONLY DO_NOT_PROMOTE for DATA_CLEANING_ALPHA_AB_FIX2_20260614 |
| Contradictory text corrected | Selector-Ready Report gate description | "improves mean IC but NOT positive fold rate" corrected to "improves both mean IC and positive fold rate" with exact values |
| Alpha count corrected | Section 9.3 | "All 7 alphas" corrected to "All 12 alphas" |
| Baseline label clarified | Section 5 | Added clarification: clean data baseline, no RA, no formulaic winner guard, no portfolio guard |
| Fallback terminology clarified | Section 4 note | Alpha-selection fallback 0/12 distinguished from winner-guard fallback (N/A for this variant) |
| Gate line updated | Header | Gate annotated as "superseded by DATA_CLEANING_ALPHA_AB_FIX2_20260614" |

### 2.2 Clean+WG Report (cpcv12_v3_winner_guard_clean_stat_validation_report_20260614.md)

| Correction | Location | Detail |
|-----------|----------|--------|
| Supersession block added | Top of report (after title) | 5-point correction block with FIX2 gate reference |
| CONDITIONAL_PROMOTE superseded | Selector-Ready Report section | Inline note: superseded by RESEARCH_ONLY DO_NOT_PROMOTE for DATA_CLEANING_ALPHA_AB_FIX2_20260614 |
| Contradictory text corrected | Selector-Ready Report gate description | "improves mean IC but NOT positive fold rate" corrected to "improves both mean IC and positive fold rate" with exact values |
| Alpha count corrected | Section 9.3 | "All 7 alphas" corrected to "All 12 alphas" |
| Baseline/no guard label clarified | Section 5 | Corrected from "Baseline (no RA, no guard)" to "Clean + Formulaic Winner Guard (formulaic_winner_guard=true, portfolio_guard=false)" with guard details |
| Fallback terminology clarified | Section 4 note | Alpha-selection fallback 0/12 distinguished from winner-guard fallback 4/12 folds 1, 2, 5, 7 |
| Guard status detailed | Section 5 | Added allowlist, fallback folds, PIT-safe confirmation |
| Gate line updated | Header | Gate annotated as "superseded by DATA_CLEANING_ALPHA_AB_FIX2_20260614" |

---

## 3. Correction Summary Matrix

| L3 Finding | Stale Text | Corrected Text | Reports Affected |
|-----------|-----------|---------------|-----------------|
| CONDITIONAL_PROMOTE conflict | `Selector Verdict: CONDITIONAL_PROMOTE` | Superseded by `RESEARCH_ONLY — DO_NOT_PROMOTE` for DATA_CLEANING_ALPHA_AB_FIX2_20260614 | Both validation reports |
| Stale alpha count | "All 7 alphas have mean OOS IC below 0.02" | "All 12 alphas have mean OOS IC below 0.02" | Both validation reports |
| Misleading clean+WG label | "Baseline (no RA, no guard)" in clean+WG | "Clean + Formulaic Winner Guard (formulaic_winner_guard=true, portfolio_guard=false)" | Clean+WG validation report |
| Clean baseline label | "Baseline (no RA, no guard)" in clean | Clarified: clean data baseline, no RA, no formulaic winner guard, no portfolio guard | Clean validation report |
| Fallback terminology | "Fallback Frequency: 0.0%" without distinction | Alpha-selection fallback 0/12 vs winner-guard fallback 4/12 folds 1,2,5,7 | Both validation reports |
| Incomplete skill listing | 3 of 9 skills listed | All 9 declared skills listed and read | This L2 report |

---

## 4. Verdict and Rationale (Unchanged from FIX1)

### `RESEARCH_ONLY — DO_NOT_PROMOTE`

**Blockers** (all must clear for promotion):

1. **Weak alpha pool**: All 12 alphas have mean IC < 0.02 across all variants. Zero alphas pass the quant-research IC gate.
2. **Research gate verdict**: All 12 alphas receive RETIRE under BH-FDR corrected statistical testing (q-values all > 0.05).
3. **Statistical validation**: Both clean variants return FAIL due to weak alpha blocker.
4. **ICIR below promotion threshold** for the clean-only variant (0.3469 < 0.5).

**Positive signals** (noted but insufficient for promotion):

- Data cleaning improves portfolio IC by +0.013 (from negative to positive).
- Winner guard on clean data further improves IC to 0.0157 and achieves ICIR 0.5067.
- Recovery-only pool outperforms full pool (mean IC +0.005, positive fold rate +33pp).
- DSR and PBO gates pass for both clean variants.

**Conclusion**: While data cleaning produces a measurable directional improvement in portfolio-level metrics, the underlying alpha pool lacks sufficient individual alpha strength (mean IC < 0.02) for promotion. The improvement is necessary but not sufficient. No production source changes are warranted.

---

## 5. Default Behavior (Unchanged)

- **`research_pool_mode`**: `"full"` (unchanged across all variants).
- **`formulaic_winner_guard`**: `false` by default (only enabled in clean+WG variant config).
- **No production code paths are affected** by this diagnostic.
- **No config defaults are changed**.

---

## 6. SOD / Audit Trail

- **Author**: Role 14 (data-scientist), L2 implementation only
- **No self-approval**: This report is research documentation, not a promotion request
- **Tier 3 submission**: Required before any production consideration
- **No production source changes made**: All corrections are report-only wording fixes applied directly to scoped validation reports
- **Reproducibility**: All metrics sourced from persisted JSON backtest results and validation reports in `.ly_state/session/` and `data/phase35_results/`
- **Write scope**: Only scoped validation reports and this L2 session report were written

---

## 7. Forbidden Path Scan (Exact Wording)

no authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

---

*Report generated 2026-06-14. L2 implementation only — submit to Tier 3 audit before any production consideration.*
