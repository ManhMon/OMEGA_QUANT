# L2 Role 14 — Alpha Recovery Diagnostics Implementation Report

**Gate**: ALPHA_RECOVERY_DIAGNOSTICS_20260614
**Role**: 14 (data-scientist) — L2 implementation only
**Date**: 2026-06-14
**Status**: Implementation complete — submitted to Tier 3 audit

---

## 1. Source Files Read (Repo-Local Only)

### Agent Definition
- `.agents/agent/data-scientist.md` — role_id: 14, tier: 2, skills: [python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow]

### Skills (All from `.agents/skills/`)
| Skill | Path | Status |
|-------|------|--------|
| python-patterns | `.agents/skills/python-patterns/SKILL.md` | Read |
| clean-code | `.agents/skills/clean-code/SKILL.md` | Read |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | Read |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | Read |
| performance-profiling | `.agents/skills/performance-profiling/SKILL.md` | Read |
| quant-research | `.agents/skills/quant-research/SKILL.md` | Read |
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` | Read |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | Read |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` | Read |

### Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source
- `.openclaw\skills` is non-authoritative and not used as source
- `C:\Users\GHC\.agents` is non-authoritative and not used as source
- `.codex\memories` is non-authoritative and not used as source

---

## 2. Implementation Summary

### Files Modified
| File | Changes |
|------|---------|
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Added alpha recovery diagnostics module: cluster classification, neutralized IC proxy, regime-conditioned IC, IC decay summary, AlphaRecoveryReport dataclass, compute_alpha_recovery_diagnostics() |
| `scripts/analyze_alpha_weakness.py` | Added `--recovery-diagnostics` and `--regime-threshold-sharpe` CLI flags; added Section 11 recovery diagnostics report generation |
| `tests/test_risk_adjusted_alpha_score.py` | Added TestClassifyAlphaCluster, TestComputeNeutralizedICProxy, TestComputeRegimeConditionedIC, TestComputeICDecaySummary, TestComputeAlphaRecoveryDiagnostics test classes |
| `tests/test_analyze_alpha_weakness.py` | Added TestRecoveryDiagnosticsOptIn test class |

### Files NOT Modified (alpha_selector.py)
`src/omega/quant/walk_forward/alpha_selector.py` — No changes needed. The selector already imports and uses `classify_research_gate_verdict` and related functions. Recovery diagnostics are analysis-only and don't affect the selector's runtime behavior.

### Generated Artifacts
| File | Description |
|------|-------------|
| `.ly_state/session/alpha_recovery_report_20260614.md` | Full diagnostics report with research gates + recovery diagnostics |

---

## 3. New Functions Added to `risk_adjusted_alpha_score.py`

### Alpha Cluster Classification
- `classify_alpha_cluster(alpha_name)` — Classifies alphas into clusters (momentum, volatility, volume, liquidity, microstructure) based on naming patterns.
- `ALPHA_CLUSTER_PATTERNS` — Pattern dictionary with order-sensitive matching.

### Neutralized IC Proxy
- `compute_neutralized_ic_proxy(alpha_fold_ics)` — Subtracts cluster-mean IC from each alpha's mean IC. Approximates alpha-specific signal after removing common cluster-level factor exposure. PIT-safe: uses only per-fold OOS IC values.

### Regime-Conditioned IC
- `compute_regime_conditioned_ic(fold_details)` — Classifies folds into bull/bear/sideways regimes using portfolio Sharpe/IC as proxy. Reports per-alpha IC per regime, regime fragility. PIT-safe: uses only fold-level OOS metrics.

### IC Decay Summary
- `compute_ic_decay_summary(alpha_fold_ics)` — Compares early-half vs late-half fold IC to assess IC trend over time. Estimates half-life for decaying alphas. PIT-safe: uses only fold ordering of OOS IC values.

### Full Recovery Diagnostics
- `AlphaRecoveryReport` dataclass — Contains all diagnostic outputs.
- `compute_alpha_recovery_diagnostics(fold_details, alpha_fold_ics)` — Main entry point combining all diagnostics. Classifies each alpha as:
  - **RECOVERABLE**: >=2 positive signal dimensions (neutralized IC, regime robustness, IC trend)
  - **RESEARCH_ONLY**: 1 positive signal dimension
  - **CONFIRMED_RETIRE**: 0 positive signal dimensions

---

## 4. Key Design Decisions

### Default Behavior Unchanged
- All new diagnostics are opt-in via `--recovery-diagnostics` CLI flag
- Default behavior of `generate_report()` and `select_alphas_risk_adjusted()` is unchanged
- No modifications to any live trading paths or production behavior

### PIT Safety Preserved
- All diagnostics use only per-fold OOS IC values already computed
- No new data access, no look-ahead
- Regime classification uses fold-level Sharpe/IC as proxy (not raw price data)

### Fallback Remains Failure
- Recovery diagnostics do not reclassify fallback usage as success
- `compute_fallback_as_failure_metrics()` behavior unchanged

### No Look-Ahead
- IC decay uses chronological fold ordering (already established by walk-forward)
- Regime classification uses only per-fold metrics (no future data)

---

## 5. Test Results

```
python -m pytest tests/test_risk_adjusted_alpha_score.py tests/test_analyze_alpha_weakness.py -q

218 passed in ~12s
0 failed
```

### New Test Classes
| Test Class | Tests | Description |
|-----------|-------|-------------|
| TestClassifyAlphaCluster | 8 | Cluster classification correctness |
| TestComputeNeutralizedICProxy | 3 | Neutralized IC computation |
| TestComputeRegimeConditionedIC | 3 | Regime-conditioned IC per alpha |
| TestComputeICDecaySummary | 4 | IC trend and half-life estimation |
| TestComputeAlphaRecoveryDiagnostics | 4 | Full diagnostics pipeline |
| TestRecoveryDiagnosticsOptIn | 7 | Opt-in behavior and CLI flags |

---

## 6. Script Execution

```
python scripts/analyze_alpha_weakness.py \
    --input-dir data/phase35_results/ab_guard_20260614_101727 \
    --output .ly_state/session/alpha_recovery_report_20260614.md \
    --research-gates --recovery-diagnostics
```

**Result**: Report written to `.ly_state/session/alpha_recovery_report_20260614.md` (516 lines)

### Key Findings from Recovery Diagnostics

Across all 3 variants (baseline, ra_guard, ra_no_guard):

| Alpha | Research Verdict | Recovery Classification |
|-------|-----------------|------------------------|
| close_auction_drift_10 | RETIRE | RECOVERABLE (positive in 2-3 regimes) |
| liquidity_provision_ratio_10 | RETIRE | RESEARCH_ONLY (improving IC trend) |
| micro_momentum_5_20 | RETIRE | RESEARCH_ONLY (improving IC trend) |
| kyle_lambda_20 | RETIRE | CONFIRMED_RETIRE |
| tick_signed_volume_imbalance_5 | RETIRE | CONFIRMED_RETIRE |
| volatility_compression_5 | RETIRE | CONFIRMED_RETIRE |
| volume_clock_acceleration_10 | RETIRE | CONFIRMED_RETIRE |

- **1 RECOVERABLE**: `close_auction_drift_10` — positive IC in all 3 regime proxies (bull, bear, sideways), not regime-fragile despite negative IC trend
- **2 RESEARCH_ONLY**: Show improving IC trend over time but lack regime robustness
- **4 CONFIRMED_RETIRE**: No positive signal dimension detected

---

## 7. Tier 3 Audit Submission

This implementation is submitted to:
- **Code Reviewer (role 21)**: Code quality, reproducibility review
- **QA Engineer (role 17)**: Model validation and testing review

**Cannot self-approve. Awaiting Tier 3 [APPROVED] verdicts.**

---

*Report generated by role 14 (data-scientist). L2 implementation only.*
