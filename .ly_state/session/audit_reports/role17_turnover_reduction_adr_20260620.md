# QA Audit Report

Role: 17 qa-engineer, Codex L3 Independent QA Review
Date: 2026-06-20
Gate: TURNOVER_REDUCTION_ADR_20260620_QA
L2 Session: l2_role7_turnover_reduction_adr_20260620
Tier 2 Engineer: 7 tech-lead
Verdict: [NEEDS_FIX]

## Source Evidence

L3 repo-local files read: .agents/agent/qa-engineer.md; .agents/skills/webapp-testing/SKILL.md; .agents/skills/testing-patterns/SKILL.md; .agents/skills/verify-changes/SKILL.md; .agents/skills/systematic-debugging/SKILL.md; .agents/skills/audit-cycle/SKILL.md.

L2 report evidence verified: .agents/agent/tech-lead.md plus repo-local clean-code, code-review-checklist, plan-writing, testing-patterns, verify-changes, and systematic-debugging SKILL.md files.

Forbidden path scan: no authoritative reliance found. L2 marks global agents, Antigravity scratch, OpenClaw, and Codex memory as forbidden or not used. L3 used repo-local role and skill files only as authoritative sources.

## SOD Checks

- Writer != auditor: PASS. L2 role_id=7, L3 role_id=17.
- L3 boundary: PASS. No production source or test files modified.
- Phase gate update: skipped per request. QA perspective only.

## Requirement Checks

- pipeline_v2 shared defaults and wiring: PASS.
- Auto-wire before BoardLotRoundingOverlay: PASS.
- Duplicate smoothing prevention: PASS.
- backtest_hybrid_regime.py updated: PASS.
- paper_trading_daily.py updated: PASS.
- docs/turnover_reduction_postmortem_note_20260620.md exists: PASS.
- First-date non-rebalance carry-forward: FAIL.

## Test Execution

Command: python -m pytest tests/test_pipeline_v2.py -k 'turnover or smoothing or throttle or carry_forward or tail_control' -v

Result: 11 passed, 36 deselected. Warnings: existing deprecations and pytest cache path warning.

## Defects Found

1. First-day non-rebalance carry-forward ignores persisted prior weights.

   Location: src/omega/quant/pipeline_v2.py:490

   Repro executed with weekly frequency, Monday rebalance, dates 2026-01-06 and 2026-01-07, persisted previous weights A=0.05 and B=-0.05, candidate first-row weights A=0.50 and B=-0.50. Observed first row remained A=0.50 and B=-0.50.

   Expected: Tuesday is not the configured Monday rebalance day, so first row should carry persisted T-1 weights or otherwise avoid new target weights until the next rebalance day.

   Cause: non-rebalance carry-forward only runs when i > 0; i == 0 falls through to candidate weights.

   Required fix: handle first row plus non-rebalance day using persisted last_weights when available, preserving columns and documented missing-symbol behavior. Add weekly and monthly tests for first-date non-rebalance plus empty previous-weight behavior.

## Verdict

[NEEDS_FIX]
