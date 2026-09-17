# Code Review Audit Report
**Role**: Code Reviewer (Role 21)
**Date**: 2026-06-30T07:30:00+07:00
**Submission**: `HYBRID_REGIME_PIT_SAFE_PRECOMPUTE_ACCEL_20260630`
**Scope**: `scripts/backtest_hybrid_regime.py`, `tests/phase35/test_hybrid_regime_memory_optim.py`, `.ly_state/session/l2_role14_pit_safe_precompute_accel_20260630.md`
**Tier 2 Engineer**: `data-scientist` (Role 14)
**L2 Session**: `l2_role14_pit_safe_precompute_accel_20260630`

## Repo-Local Files Read
- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/agent/data-scientist.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `scripts/backtest_hybrid_regime.py`
- `tests/phase35/test_hybrid_regime_memory_optim.py`
- `.ly_state/session/l2_role14_pit_safe_precompute_accel_20260630.md`
- `.ly_state/session/phase_gates.json`
- `scripts/sod_gate_enforcer.py`

## Forbidden Path Scan Result
- No authoritative reliance on forbidden non-repo-local sources.
- `.gemini\antigravity-ide\scratch\ag-kit` not read; non-authoritative only.
- `.openclaw\skills` not read; non-authoritative only.
- `C:\Users\GHC\.agents` present but non-authoritative only; not used as role/skill source.
- `.codex\memories` not read; non-authoritative only.
- No Antigravity scratch reads/writes.

## SOD Evidence
- Writer != auditor verified: `l2_role_id=14`, `l3_role_id=21`, `14 != 21`.
- L3 boundary respected: source/tests reviewed read-only; writes limited to `.ly_state/session/audit_reports/` and target `phase_gates.json` entry.
- L2 report lists repo-local role/skill evidence from `.agents/agent/data-scientist.md` plus declared repo-local `SKILL.md` files.

## Checks
- Scope compliance: code changes stayed within approved source/test scope.
- `python -m py_compile "scripts/backtest_hybrid_regime.py" "tests/phase35/test_hybrid_regime_memory_optim.py"`: pass.
- `pytest tests/phase35/test_hybrid_regime_memory_optim.py -q`: `5 passed`.
- PIT boundary review:
  - `pred_lag_df` remains full-panel per-symbol `shift(1)` for prediction only (`scripts/backtest_hybrid_regime.py:719-745`).
  - HMM still slices `close_pivot_full` by `train_dates` before fitting (`scripts/backtest_hybrid_regime.py:976-984`).
  - Ridge training still recomputes train-only lags from `train_feat` (`scripts/backtest_hybrid_regime.py:1099-1103`).
- Windows memory path review:
  - `joblib` backend switched to `threading` for shared-memory reuse (`scripts/backtest_hybrid_regime.py:2339-2349`).
  - `train_fold_models()` documents no mutation of shared `feat_df` and returns `composite_signal` separately (`scripts/backtest_hybrid_regime.py:896-900`, `1322-1346`).
  - No obvious cross-fold file race in scoped code; per-fold state dir remains isolated (`scripts/backtest_hybrid_regime.py:1752-1760`).

## Findings
1. **Blocking - stale disk cache key can silently reuse wrong precomputes**  
   `scripts/backtest_hybrid_regime.py:766-782`, `814-817`  
   `build_precompute_cache_key()` hashes only date range, universe flags, row/symbol counts, date bounds, and alpha column names. It does **not** fingerprint the actual feature values, close values, or upstream feature-data version. A later `p2full` run with changed alpha/close content but the same shape/schema will hit the same key and reuse stale `pred_lag_df` / `close_pivot_full` from disk. That breaks correctness and makes the cache non-auditable for PIT use across reruns. Current tests only prove round-trip equality for unchanged fixtures and do not cover cache invalidation after input-content changes.

## CODEX AUDIT VERDICT
**Status:** [NEEDS_FIX]
**Date:** 2026-06-30T07:30:00+07:00
**Auditor:** Codex (L3)
**Scope:** PIT-safe shared precompute cache + Windows threading backend review

### Phase Gates
- **l3_session_id:** `l3_role21_hybrid_regime_pit_safe_precompute_accel_20260630_20260630`
- **l3_session_key:** `l3_role21_hybrid_regime_pit_safe_precompute_accel_20260630_20260630`
- **audit_report_path:** `.ly_state/session/audit_reports/role21_hybrid_regime_pit_safe_precompute_accel_20260630_20260630.md`
- **final_verdict:** [NEEDS_FIX]

### Compliance Checks
- [x] Writer/auditor separation verified
- [x] Scope matched approved files
- [x] `py_compile` passed
- [x] Targeted pytest passed
- [x] No global fold-trained cache introduced
- [x] L2 repo-local skill source evidence verified
- [ ] Cache invalidation/correctness sufficient for approval

### Required Actions
1. Strengthen the disk-cache key or validation so cache reuse depends on actual panel content or authoritative upstream artifact version, not just schema/shape/date bounds.
2. Add a targeted regression test proving stale cache is not reused when alpha/close values change under otherwise identical metadata.

**Signature:** Codex L3 Auditor
