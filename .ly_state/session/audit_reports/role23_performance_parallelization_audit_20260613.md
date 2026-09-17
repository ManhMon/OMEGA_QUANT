# Performance Test Audit Report

**Role**: performance-tester (Role 23, Tier 3, Codex)
**Date**: 2026-06-13
**Gate**: PERFORMANCE_PARALLELIZATION_AUDIT_20260613
**L2 Session**: l2_role16_performance_parallelization_audit_20260613
**L2 Role**: machine-learning-engineer (Role 16, Tier 2, OpenCode)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/performance-tester.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/webapp-testing/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.ly_state/session/l2_role16_performance_parallelization_audit_20260613.md`
- `src/omega/infra/resource_manager.py`
- `src/omega/quant/evolution/feature_adapter.py`
- `src/omega/quant/evolution/genetic_engine.py`
- `scripts/backtest_evolution.py`
- `scripts/backtest_evolution_multiseed.py`
- `scripts/backtest_evolution_integration.py`

## SOD Checks

- L3 role spec validated: `role_id=23`, `tier=3`, `platform=Codex`, `sod_boundary` present.
- Writer != auditor verified: L2 role 16 != L3 role 23.
- L3 write boundary respected: this audit writes only this report and the scoped `phase_gates.json` entry.
- Forbidden path scan for L3: CLEAN - forbidden paths are non-authoritative and not used as source.
- L2 repo-local evidence is not valid as written: the L2 report claims no Antigravity scratch reads at lines 30-37, but lists `C:\Users\GHC\.gemini\antigravity-ide\brain\74b0ccc4-e8b5-4349-be91-16a601fab790\implementation_plan.md` as an implementation plan read at lines 57-58. This contradicts the strict repo-local source contract and scratch path prohibition.

## Findings

1. **HIGH - Feature cache can return stale features for changed input panels.**
   `src/omega/quant/evolution/feature_adapter.py:96-110` fingerprints only shape, sorted column names, first row, last row, and `top_n_features`. `compute_all()` then returns cached results at lines 129-132 and stores them at lines 209-210. Any changed middle row with same first/last rows reuses stale arrays. Repro command changed the second row `close` from `2.0` to `200.0`; the second call returned cached `close[1]=2.0` and `same_obj=True`. This violates feature cache correctness and can corrupt walk-forward/evolution results. It also creates PIT/split contamination risk when distinct train/test/fold panels share shape/endpoints.

2. **HIGH - L2 forbidden-path evidence contradicts the gate contract.**
   `.ly_state/session/l2_role16_performance_parallelization_audit_20260613.md:30-37` states the scan is CLEAN and no Antigravity scratch files were read. Lines 57-58 list an Antigravity scratch implementation plan path. Under `STRICT_REPO_LOCAL_SKILL_LOADING_20260612`, forbidden paths may only appear as non-authoritative/scan evidence, not as implementation-plan source material. Gate cannot approve until L2 report/evidence is corrected by a new L2 cycle.

## Checks

- Worker cap/resource logic: `compute_safe_workers()` returns at least 1 and caps by CPU fraction, available RAM if `psutil` is present, and hard cap. No blocking issue found.
- Import path fixes: `scripts/backtest_evolution.py` and `scripts/backtest_evolution_integration.py` now use `ROOT / "src"`; integration test passed. Deprecated old alpha import paths resolve to the same functions as the new modular imports.
- Progress metadata: `genetic_engine.py` adds elapsed/generation/ETA fields after history append. Observational only; no semantic issue found.
- Benchmark claims: requested reruns passed; reported full-pipeline metrics are broadly supported by current rerun (`Duration=0.590s`, `Sharpe=1.6795`).
- Scope: scoped diff changes are limited to the six production/script files named in the audit scope. The wider worktree is dirty (`git diff --name-only` count: 238), so unrelated dirty state remains outside this gate assessment.

## Test Results

- `python -m pytest tests/test_feature_adapter_nonnumeric.py -q` -> PASS, 6/6.
- `python -m pytest tests/test_dashboard_data_control_integration.py -q` -> PASS, 106/106.
- `python scripts/run_backtest.py evolution-integration` -> PASS, 6/6.
- `python scripts/run_backtest.py full-pipeline` -> PASS, Sharpe 1.6795, duration 0.590s.
- Cache correctness repro -> FAILS expected fresh recomputation: changed middle row is ignored by fingerprint and stale cached result is returned.
- `python scripts/sod_gate_enforcer.py` -> not run after gate update because verdict is `[NEEDS_FIX]`; final enforcer is only appropriate after approval.

## Required Fix

- Replace the feature cache key with a correctness-preserving identity/content strategy. At minimum, avoid returning cached data for a different DataFrame object or hash full relevant data content with index/order included. Do not use first/last-row-only fingerprints for feature outputs.
- Add a regression test proving that a middle-row data change recomputes features or misses cache.
- Correct the L2 report through a new L2 session so forbidden paths are not listed as implementation sources, or are explicitly documented only as non-authoritative violation/scan evidence if relevant.

## Verdict

[NEEDS_FIX]
