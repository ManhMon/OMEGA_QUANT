# L2 Role 14 — Baseline Risk/Sizing OOS Execution 2026-06-16

**GATE:** BASELINE_RISK_SIZING_OOS_EXECUTION_20260616
**Role:** 14 (Data Scientist, Tier 2, OpenCode L2 Execution)
**Date:** 2026-06-16
**Status:** OOS EXECUTED — 3 variants, 12-fold each, all completed successfully.

---

## Files Read - Repo-Local Skill Source Evidence

| File | Repo-Relative Path |
|------|-------------------|
| Agent definition | `.agents/agent/data-scientist.md` |
| python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| clean-code | `.agents/skills/clean-code/SKILL.md` |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| performance-profiling | `.agents/skills/performance-profiling/SKILL.md` |
| quant-research | `.agents/skills/quant-research/SKILL.md` |
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |

no authoritative reliance; .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source.

---

## OOS Execution Summary

### Prior Blocker (Resolved)

Previous OOS attempt blocked by `OSError: [WinError 1455] The paging file is too
small for this operation to complete` during PyTorch import chain. Current
execution completed all 3 variants × 12 folds without error. No paging issue
recurred.

### Configuration (Identical Across All Variants)

| Parameter | Value |
|-----------|-------|
| Folds | 12 (3yr train, 1yr test) |
| Top-N symbols | 30 |
| Formulaic alphas | v3_pruned (5 alphas) |
| Winner guard | ON |
| Dynamic universe | ON |
| Drawdown control | ON (10% threshold) |
| XGBoost | OFF |
| Risk-sizing overlay | ON (variant-specific flags) |

### Variant Results vs Dynamic Baseline

| Metric | Baseline | Inverse-Vol | Confidence | Both |
|--------|----------|-------------|------------|------|
| Portfolio IC | 0.0249 | **0.0291** | 0.0151 | **0.0280** |
| Sharpe | 3.1106 | **3.9845** | 3.0673 | **3.3736** |
| MaxDD | -12.25% | **-11.92%** | **-11.77%** | -12.39% |
| Avg PnL (VND) | 615,993,405 | **822,021,832** | **632,191,405** | **731,893,443** |
| **Strict Gate** | — | **PASS** | FAIL | FAIL |

### Strict Promotion Gate

Requirement: beat baseline on ALL of Sharpe AND PnL AND MaxDD simultaneously.

- **Inverse-Vol Only: PASS** — Sharpe 3.9845 > 3.1106, PnL 822M > 616M, MaxDD -11.92% > -12.25%
- Confidence Only: FAIL — Sharpe 3.0673 < 3.1106
- Both: FAIL — MaxDD -12.39% < -12.25%

### Status: RESEARCH-ONLY

Only inverse-vol variant passes the strict gate. No promotion to live or default.
Submitted to Tier 3 audit (Code Reviewer role 21 + QA Engineer role 17).

---

## Artifacts

| Artifact | Path |
|----------|------|
| IVOL result JSON | `data/phase35_results/phase35_backtest_results_risk_sizing_ivol_20260616_baseline.json` |
| IVOL summary TXT | `data/phase35_results/phase35_backtest_summary_risk_sizing_ivol_20260616_baseline.txt` |
| CONF result JSON | `data/phase35_results/phase35_backtest_results_risk_sizing_conf_20260616_baseline.json` |
| CONF summary TXT | `data/phase35_results/phase35_backtest_summary_risk_sizing_conf_20260616_baseline.txt` |
| BOTH result JSON | `data/phase35_results/phase35_backtest_results_risk_sizing_both_20260616_baseline.json` |
| BOTH summary TXT | `data/phase35_results/phase35_backtest_summary_risk_sizing_both_20260616_baseline.txt` |
| Execution report | `.ly_state/session/baseline_risk_sizing_oos_execution_report_20260616.md` |

---

## SOD Boundary

No self-approval. Tier 3 audit required (Code Reviewer + QA Engineer).
No live promotion until strict OOS evidence + audit approval.
