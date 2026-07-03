# Compliance Audit Report

**Role**: compliance-officer (Role 20, Codex L3)
**Date**: 2026-06-14T00:38:34+07:00
**Gate**: RISK_ADJUSTED_ALPHA_SELECTION_20260614
**L2 Session**: l2_role16_risk_adjusted_alpha_selection_20260614
**L2 Role**: machine-learning-engineer (Role 16, OpenCode)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- .agents/agent/compliance-officer.md
- .agents/agent/machine-learning-engineer.md
- .agents/skills/audit-cycle/SKILL.md
- .agents/skills/vulnerability-scanner/SKILL.md
- .agents/skills/vulnerability-scanner/checklists.md
- .agents/skills/code-review-checklist/SKILL.md
- .agents/skills/omega-sod/SKILL.md
- .agents/skills/sops/SKILL.md
- .agents/skills/python-patterns/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/performance-profiling/SKILL.md
- .agents/skills/systematic-debugging/SKILL.md
- .agents/skills/ml-dl-rl/SKILL.md
- .agents/skills/backtesting-pit-safety/SKILL.md
- .agents/skills/vietnam-market-data/SKILL.md

Note: sops/SKILL.md references SOP_AC.md, SOP_BACKTEST.md, and SOP_PIT_SAFETY.md, but those repo-local files were not present at .agents/skills/sops/. The embedded SOP content in sops/SKILL.md was reviewed.

## Forbidden Path Scan

Clean: forbidden paths are non-authoritative and not used as source. L2 report states Antigravity scratch/OpenClaw/Codex memory/global Codex agents were not accessed. L3 did not use those paths as authoritative sources.

## SOD Checks

- Writer != auditor: PASS, L2 role_id 16 != L3 role_id 20.
- L3 role: PASS, role20 has tier=3, platform=Codex, sod_boundary present.
- L2 role: PASS, role16 has tier=2, platform=OpenCode.
- Scope: PASS, reviewed named source/test/report files only.
- Paper-trading-only boundary: PASS for implementation surface; no live execution/order-routing integration found in scoped code.
- L3 write boundary: PASS for manual changes; only this audit report and phase_gates.json are updated by L3. Required smoke commands may write their normal runtime result artifacts under data/phase35_results/.

## Test Evidence

- `python -m pytest tests/test_risk_adjusted_alpha_score.py -q`: PASS, 41 passed, 3 warnings.
- `python scripts/run_phase35_backtest.py --quick-mode --no-xgboost`: PASS; config logged `Risk-Adjusted Alpha Selection: False`; no `[RiskAdj]` selection logs observed.
- `python scripts/run_phase35_backtest.py --quick-mode --no-xgboost --risk-adjusted-alpha-selection`: PASS; config logged `Risk-Adjusted Alpha Selection: True`; observed `[RiskAdj] Selected 1/7 alphas: gate=PASS` and `[RiskAdj] Selected 4/7 alphas: gate=PASS`.

## Findings

### 1. BLOCKING - Enabled run does not persist risk-adjusted selection evidence

Locations:
- src/omega/quant/alpha/phase35.py:1978
- src/omega/quant/alpha/phase35.py:1986
- src/omega/quant/alpha/phase35.py:2259
- scripts/run_phase35_backtest.py:350

The enabled path computes `ra_result`, but only `ra_result.selected_alphas` is used to set `top_alphas`. The `RiskAdjustedSelectionResult` object is then dropped. `FoldMetrics` has no risk-adjusted evidence field, the metrics object does not persist it, and the backtest JSON only records `config.risk_adjusted_alpha_selection`.

Actual saved JSON after the enabled smoke run contains no `selected_alphas`, `rejected_alphas`, `paper_trading_gate`, `paper_trading_reasons`, or `score_breakdowns`. This fails the requested output evidence completeness check and prevents downstream audit from reconstructing why each alpha was accepted/rejected.

Required fix: persist per-fold risk-adjusted evidence when opt-in is enabled, either in `FoldMetrics`/`fold_details` or a deterministic companion evidence artifact. It must include selected alphas, rejected alphas with reasons, paper-trading gate/reasons, score breakdowns, and config used.

### 2. BLOCKING - `to_dict()` omits `raw_expected_sharpe`

Location:
- src/omega/quant/walk_forward/risk_adjusted_alpha_score.py:107

`AlphaScoreBreakdown` stores `raw_expected_sharpe`, but `RiskAdjustedSelectionResult.to_dict()` does not serialize it. The L2 report claims evidence contains all six component scores plus raw values. Current serialization includes `raw_max_drawdown` but omits the raw expected Sharpe value.

Required fix: add `raw_expected_sharpe` to serialized score breakdowns and add a regression test for it.

## PIT / Compliance Notes

- PIT design is acceptable in the audited paths: selection data is derived from embargoed `train_df_clean`, then split into `train_actual` and `val_actual`; test data is not passed into `risk_adjusted_select()`.
- Opt-in/default disabled behavior is acceptable: constructor default is `False`; CLI uses `store_true`.
- Smoke tests validate disabled and enabled paths execute.
- The feature remains paper-trading-only in scoped code; no live execution call path was added.

## Verdict

[NEEDS_FIX]

Composite selection executes and appears PIT-safe, but the gate cannot be approved because required output evidence is not persisted and serialized evidence omits one raw component.
