# Compliance Audit Report

**Role**: compliance-officer (Role 20, Codex L3)
**Date**: 2026-06-15T06:22:27+07:00
**Gate**: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
**L2 Session**: l2_role14_regime_conditioned_alpha_routing_20260615
**L2 Role**: data-scientist (Role 14, OpenCode L2)

## Repo-Local Sources Read

- .agents/agent/compliance-officer.md
- .agents/skills/audit-cycle/SKILL.md
- .agents/skills/vulnerability-scanner/SKILL.md
- .agents/skills/code-review-checklist/SKILL.md
- .agents/skills/omega-sod/SKILL.md
- .agents/skills/sops/SKILL.md
- .agents/agent/data-scientist.md
- .ly_state/session/l2_role14_regime_conditioned_alpha_routing_20260615.md

Forbidden path scan: no authoritative reliance; .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source.

## Checks

- Writer != auditor: PASS. l2_role_id=14, l3_role_id=20.
- Scope compliance: PASS. Reviewed src/omega/quant/alpha/phase35.py, scripts/run_phase35_backtest.py, tests/phase35/test_regime_routing.py, and L2 report.
- Opt-in/default disabled: PASS. Engine default is regime_routing_enabled=False; CLI uses --enable-regime-routing store_true and persists config.
- PIT safety: PASS. Regime features use per-ticker returns shifted by one period before cross-sectional aggregation; per-regime IC estimation merges only train_df with ex-ante regime labels; routing uses test dates, regime labels, and train ICs, not test returns.
- Train-only routing evidence: PASS. _estimate_regime_ic receives train_df only. _apply_regime_routing receives regime_ics/train_ics and does not inspect return_col or test returns.
- Fallback baseline behavior: PASS. Insufficient train regime days, low regime IC, missing labels, or exceptions leave scale=1.0 and record fallback evidence.
- JSON evidence: PASS. FoldMetrics.regime_routing_evidence is persisted by serialize_fold_details and output config includes regime_routing_enabled, regime_routing_min_train_days, regime_routing_min_ic.
- CLI/config: PASS. Flags and engine wiring present.
- Live/default promotion: PASS. Routing remains research-only opt-in; no default live promotion detected.
- SOD: PASS. L2 report lists repo-local skill sources and forbidden-path evidence; L3 modified only this audit report and phase_gates.json.

## Tests Run

- python -m pytest tests/phase35/test_regime_routing.py -q: 41 passed.
- python -m pytest tests/phase35/test_drawdown_control_default_on_cli.py tests/phase35/test_xgboost_default_off_cli.py -q: 49 passed.
- python -m pytest tests/phase35 -q: 579 passed.

Warnings observed: existing deprecation/cache/pandas/scipy warnings only; no failures.

## Verdict

[APPROVED]

