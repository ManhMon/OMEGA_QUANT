# Compliance Audit Report

**Role**: compliance-officer (Role 20, Codex L3)
**Date**: 2026-06-15T00:00:00+07:00
**Gate**: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615
**L2 Session**: l2_role14_automated_alpha_discovery_dynamic_20260615
**L2 Role**: data-scientist (Role 14, OpenCode L2)
**Scope**: automated alpha discovery factory, transfer diagnostics, Phase35 wiring, CLI, tests, reports, gate metadata

## Repo-Local Sources Read

- .agents/agent/compliance-officer.md
- .agents/skills/audit-cycle/SKILL.md
- .agents/skills/vulnerability-scanner/SKILL.md
- .agents/skills/code-review-checklist/SKILL.md
- .agents/skills/omega-sod/SKILL.md
- .agents/skills/sops/SKILL.md

Forbidden path scan: no authoritative reliance. Mentions of `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` appear only in repo-local contract text or L2 forbidden-path evidence; none were used as authoritative role or skill sources.

## SOD Checks

- Writer != auditor: PASS. L2 role_id=14, L3 role_id=20.
- L3 boundary: PASS. No production source/test edits made by L3.
- L2 repo-local skill evidence: PASS. L2 report lists data-scientist role spec plus all 9 declared repo-local skills.
- L2 report path: .ly_state/session/l2_role14_automated_alpha_discovery_dynamic_20260615.md

## Test Evidence

- `python -m pytest tests/phase35/test_automated_alpha_discovery.py -q --tb=line`: 52 passed, warnings only.
- `python -m pytest tests/phase35/test_nonredundant_alphas.py tests/phase35/test_diversified_basket.py -q --tb=line`: 119 passed, warnings only.

## Findings

1. BLOCKING - PIT/global shift leakage in template expressions.
   - Location: src/omega/quant/alpha/automated_alpha_discovery.py:62, src/omega/quant/alpha/automated_alpha_discovery.py:89, src/omega/quant/alpha/automated_alpha_discovery.py:95
   - Evidence: expressions call `df.groupby('ticker')['close'].shift(1).pct_change(...)` and `_compute_rsi_safe()` then calls `close.diff()` globally. After the group shift, `pct_change()` / `diff()` are no longer grouped by ticker, so sorted panel rows can compare one ticker against another ticker. A minimal panel reproduced cross-ticker values `[nan, nan, nan, 99.0, -0.98, 99.0]` for a 1-period momentum expression, confirming global row leakage.
   - Impact: violates the explicit `no global shift leakage` and PIT-safe requirements; generated IC evidence can be contaminated by cross-ticker artifacts.

2. BLOCKING - multiple default templates use current-bar OHLCV while evidence reports `pit_safe: True`.
   - Location: src/omega/quant/alpha/automated_alpha_discovery.py:67, src/omega/quant/alpha/automated_alpha_discovery.py:71, src/omega/quant/alpha/automated_alpha_discovery.py:73, src/omega/quant/alpha/automated_alpha_discovery.py:74, src/omega/quant/alpha/automated_alpha_discovery.py:77, src/omega/quant/alpha/automated_alpha_discovery.py:79
   - Evidence: templates read same-row `close`, `volume`, `high`, `low`, and `open`; line 73 also uses ungrouped `df['close'].shift(1)`. SOP_PIT_SAFETY requires features for time T to use only data available at T-1 or earlier.
   - Impact: look-ahead/current-bar leakage can enter screening and selected candidate metadata, while result evidence still marks `pit_safe: True` at src/omega/quant/alpha/automated_alpha_discovery.py:527.

## Checks

- Default off: PASS. Factory and Phase35 defaults are disabled.
- Candidate cap default 200: PASS.
- Deterministic generation: PASS for ordering/config; no stochastic candidate expansion beyond deterministic template order observed.
- Correlation filter: PASS structurally, train-data only when caller supplies train data.
- Train-only screening/no OOS winner selection: PARTIAL. API is named `train_df`, but PIT violations above block approval.
- No live/default promotion: PASS. No live promotion path found; CLI is research-only.
- Transfer diagnostics: PASS with caller-provided train-only data; no independent future data access found.

## Verdict

[NEEDS_FIX]

Required fix: make every template strictly ticker-grouped and T-1 lagged, including post-shift `pct_change()` / `diff()` / rolling operations; remove or lag same-row OHLCV templates; add tests that fail on cross-ticker global shift leakage and current-bar usage before re-audit.
