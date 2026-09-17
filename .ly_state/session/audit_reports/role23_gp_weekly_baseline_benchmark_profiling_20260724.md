# Performance Test Re-Audit Report

- Verdict: **[APPROVED]**
- Gate: `gp_weekly_baseline_benchmark_profiling`
- L2 session: `l2_role16_gp_weekly_baseline_benchmark_profiling_20260724`
- L2 role: `16 machine-learning-engineer`
- L3 role: `23 performance-tester`
- Re-audit: second re-audit after narrow evidence remediation
- Timestamp: `2026-07-24T21:21:59+07:00`

## Authoritative Files Read

- `.agents/AGENTS.md`
- `.agents/agent/performance-tester.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/webapp-testing/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/agent/machine-learning-engineer.md`
- `scripts/profile_bottlenecks.py`
- `scripts/measure_perf_baseline.py`
- `scripts/profile_performance.py`
- `scripts/run_weekly_evolution.py`
- `.ly_state/session/l2_role16_gp_weekly_baseline_benchmark_profiling_20260724.md`
- `.ly_state/session/gp_gate1_full_workload_baseline.json`
- `.ly_state/session/gp_gate1_bottlenecks.json`
- `.ly_state/session/gp_gate1_bottlenecks.prof`
- `.ly_state/session/gp_gate1_full_workload_runs/run_01.log`
- `.ly_state/session/gp_gate1_full_workload_runs/run_02.log`
- `.ly_state/session/gp_gate1_full_workload_runs/run_03.log`
- `.ly_state/session/gp_gate1_full_workload_runs/run_04.log`
- `.ly_state/session/phase_gates.json`

Forbidden-path scan: **PASS**. `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` were treated only as explicitly non-authoritative scan evidence. No forbidden source was read or relied upon.

## Checks

- **PASS ? SoD:** `l2_role_id=16 != l3_role_id=23`.
- **PASS ? Allowlist:** Gate work is confined to the three measurement/profiling scripts, scoped report, benchmark/profile artifacts, run logs, this audit report, and this gate object. `scripts/run_weekly_evolution.py` contains unrelated pre-existing production changes; no Gate 1 optimization edit is claimed there.
- **PASS ? L2 skills:** All eight role-16 skills are listed using repo-relative `.agents/skills/.../SKILL.md` paths only.
- **PASS ? Forbidden mentions:** Every forbidden path in the L2 report is explicitly marked non-authoritative scan evidence.
- **PASS ? Compile:** `python -m py_compile scripts/measure_perf_baseline.py scripts/profile_performance.py scripts/profile_bottlenecks.py scripts/run_weekly_evolution.py` exited `0`.
- **PASS ? Baseline contract:** Exactly one warm-up plus three measured full-workload runs. Median wall clock `25.8017136999988s`; maximum process-tree RSS `1731.09375 MB`.
- **PASS ? Run support:** Four logs show identical dimensions: `1,771,502` input rows, `30` tickers, `80,539` feature rows, `203` feature columns.
- **PASS ? Remediated blocker:** JSON `profile_top` is non-empty. JSON and `.prof` agree on `59,387,111` total calls, `58,310,158` primitive calls, `41.4155157s` runtime (`41.416s` rendered), and top cumulative hotspot ordering.
- **PASS ? Report fidelity:** L2 figures match persisted baseline, JSON, `.prof`, and run logs exactly at reported precision.
- **PASS ? Production behavior:** Gate-specific source changes are measurement/profiling harness changes only. No production optimization behavior change belongs to this gate.
- **PASS ? PIT safety:** Fixed chronological window and existing per-symbol lag behavior remain unchanged by Gate 1 work.

## Hotspot Evidence

1. `UnifiedFeatureAdapter.generate_all` ? `33.793s`
2. `AlternativeDataFetcher.generate_all` ? `21.676s`
3. `AlternativeDataFetcher._derive_sentiment_indicators` ? `21.392s`
4. `vsi_engine.calculate_sentiment` ? `17.351s`
5. `vsi_engine._calculate_sentiment_frame` ? `14.285s`
6. `arsenal.compute_ultimate_alphas` ? `10.521s`
7. `vsi_engine._resolve_source_weights` ? `7.895s`

## Verdict

**[APPROVED]** ? Narrow evidence remediation resolves the remaining machine-readable profiling blocker. L1 must run `python scripts/sod_gate_enforcer.py` after this gate update.
