# L2 Role 14 — Baseline Risk/Sizing Optimization

**GATE:** BASELINE_RISK_SIZING_OPTIMIZATION_20260616
**Role:** 14 (Data Scientist, Tier 2)
**Date:** 2026-06-16
**Status:** IMPLEMENTED — OPT-IN, DEFAULT-OFF

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

## Objective

Improve Sharpe/PnL/MaxDD via PIT-safe risk/sizing controls overlaid on the
trusted dynamic baseline, without adding new alpha signals.

## Trusted Dynamic Baseline

| Metric | Value |
|--------|-------|
| Portfolio IC | 0.0249 |
| Median IC (approx) | 0.0167 |
| Raw Signal IC | 0.0200 |
| Raw Signal Daily CS IC | 0.0216 |
| Sharpe | 3.1106 |
| Max DD | -12.25% |
| Avg PnL | ~616M VND |
| Folds | 12 (3yr train, 1yr test) |

Source: `phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json`

## Implementation Summary

### Risk/Sizing Overlay (NEW)

**Module:** `src/omega/quant/walk_forward/risk_sizing_overlay.py`
**Integration:** `src/omega/quant/alpha/phase35.py` (Phase35WalkForwardEngine)
**CLI:** `scripts/run_phase35_backtest.py`

Two independent, opt-in, default-off features:

1. **Inverse-volatility sizing**: 1/realized_vol weights (trailing 20d, floor 0.3)
2. **Confidence scaling**: Scale exposure by rolling IC (trailing 60d, [0.3, 1.2])

### Existing Knob Analysis

| Knob | Current | Analysis |
|------|---------|----------|
| DD threshold | 10% | Well-calibrated; 8% may marginally help MaxDD |
| Sector cap | 40% | Generous; 25-30% could reduce concentration |
| Top-N stocks | 15 | Balanced |
| Rebalance freq | 7 | P9 dynamic already active |

## Test Results

| Suite | Tests | Pass | Fail |
|-------|-------|------|------|
| Risk sizing overlay (NEW) | 21 | 21 | 0 |
| Phase35 full regression | 911 | 911 | 0 |

## OOS Status

NOT EXECUTED — system constraint (paging file too small for PyTorch chain).
Full 12-fold OOS deferred to system with sufficient resources.

## SOD Boundary

- No self-approval
- Tier 3 audit required (Code Reviewer role 21 + QA Engineer role 17)
- No live promotion until strict OOS evidence + audit approval
