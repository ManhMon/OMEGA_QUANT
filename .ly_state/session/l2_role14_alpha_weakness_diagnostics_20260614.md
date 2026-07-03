# L2 Role Report — Role 14 (data-scientist)

**Gate**: ALPHA_WEAKNESS_DIAGNOSTICS_20260614  
**Date**: 2026-06-14  
**Status**: IMPLEMENTED — Submitted to Tier 3 Audit  
**SOD Boundary**: Implementation only, no self-approval

---

## Source Files Read (Repo-Local)

### Agent Definition
- `.agents/agent/data-scientist.md` — role 14, tier 2, OpenCode

### Skills Read (from `.agents/skills/`)
| Skill | Path |
|-------|------|
| python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| quant-research | `.agents/skills/quant-research/SKILL.md` |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |

### Forbidden Path Scan
| Path | Result |
|------|--------|
| `.gemini/antigravity-ide/scratch/ag-kit` | NOT accessed — non-authoritative |
| `.openclaw/skills` | NOT accessed — non-authoritative |
| `C:\Users\GHC\.agents` | NOT accessed — non-authoritative |
| `.codex/memories` | NOT accessed — non-authoritative |

**Forbidden path scan: PASS** — No non-authoritative skill sources were loaded.

---

## Implementation Summary

### Files Created/Modified
| File | Action | Purpose |
|------|--------|---------|
| `scripts/analyze_alpha_weakness.py` | Created | Main diagnostics script (~420 LOC) |
| `tests/test_analyze_alpha_weakness.py` | Created | Unit + integration tests (29 tests) |
| `.ly_state/session/alpha_weakness_diagnostics_20260614.md` | Generated | Output diagnostics report |
| `.ly_state/session/l2_role14_alpha_weakness_diagnostics_20260614.md` | This file | L2 role report |

### Data Sources
- Input: `data/phase35_results/ab_guard_20260614_101727/`
  - `baseline_phase35_backtest_results_xgboost.json`
  - `ra_guard_phase35_backtest_results_xgboost.json`
  - `ra_no_guard_phase35_backtest_results_xgboost.json`

---

## Diagnostics Scope

The script analyzes 3 variants (baseline, ra_guard, ra_no_guard) across 8 walk-forward folds and produces:

1. **Per-variant summary** — IC, Sharpe, DD, return, PnL
2. **Fold-level IC/Sharpe/DD** — Detailed per-fold breakdown
3. **Positive fold rate** — % of folds with positive IC, Sharpe, return
4. **Fallback frequency** — How often gate criteria forced fallback
5. **Guard accepted/rejected/false positives** — Portfolio guard analysis
6. **Alpha selection stability** — How consistently each alpha is selected/rejected
7. **Weak alpha ranking** — Alphas ranked by mean OOS IC (weakest first)
8. **Cross-variant comparison** — Alpha IC comparison across variants
9. **Recommended gates** — Alpha-level, variant-level, system-level recommendations

---

## Key Findings

| Metric | Baseline | RA+Guard | RA+NoGuard |
|--------|----------|----------|------------|
| Avg IC | 0.0024 | -0.0159 | -0.0071 |
| Avg Sharpe | 0.89 | 0.97 | 0.61 |
| Positive IC Rate | 50% | 37.5% | 37.5% |
| Fallback Rate | 62.5% | 87.5% | 87.5% |

- All 7 alphas below 0.02 IC gate
- `close_auction_drift_10` is the best alpha (IC ~0.02, 62.5% positive)
- `volatility_compression_5` should be retired (IC ~-0.03)
- Guard rejected RA basket in 5/8 folds with 2 false positives
- No production model changes recommended

---

## Verification Commands and Results

### Tests
```
$ python -m pytest tests/test_analyze_alpha_weakness.py -v --tb=short
======================== 29 passed, 1 warning in 0.40s ========================
```

### Script Execution
```
$ python scripts/analyze_alpha_weakness.py \
    --input-dir data/phase35_results/ab_guard_20260614_101727 \
    --output .ly_state/session/alpha_weakness_diagnostics_20260614.md
[INFO] Discovered 3 variant(s): ['baseline', 'ra_guard', 'ra_no_guard']
[INFO] Loading baseline: ...
[INFO] Analyzed baseline: 8 folds
[INFO] Loading ra_guard: ...
[INFO] Analyzed ra_guard: 8 folds
[INFO] Loading ra_no_guard: ...
[INFO] Analyzed ra_no_guard: 8 folds
[INFO] Report written to .ly_state\session\alpha_weakness_diagnostics_20260614.md
```

### Output Verification
- Report file: `.ly_state/session/alpha_weakness_diagnostics_20260614.md` (232 lines)
- Contains all 9 required sections
- No production model behavior changes made

---

## Tier 3 Audit Submission

This work is submitted to:
- **Code Reviewer (role 21)**: Code quality, reproducibility review
- **QA Engineer (role 17)**: Model validation, testing review

**Cannot proceed until all relevant Tier 3 roles return [APPROVED].**

---

*Role 14 (data-scientist) — L2 implementation only, no self-approval.*
