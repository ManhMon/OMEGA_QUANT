# L2 Gate 1 Report: Weekly Baseline Benchmark + Profiling

- Session: `l2_role16_gp_weekly_baseline_benchmark_profiling_20260724`
- Role: `16 machine-learning-engineer`
- Platform/tier: `OpenCode L2`
- Gate: `gp_weekly_baseline_benchmark_profiling`
- Scope: measurement/profiling only; no production algorithm optimization
- Status: **Gate 1 evidence consistency remediation complete; submitted for L3 audit.**

## Authoritative Sources Read

Role frontmatter parsed first. Exact repo-local files read:

- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

Parsed frontmatter:

```yaml
name: machine-learning-engineer
role_id: 16
tier: 2
platform: OpenCode
skills: [python-patterns, clean-code, testing-patterns, performance-profiling, systematic-debugging, ml-dl-rl, backtesting-pit-safety, vietnam-market-data]
sod_boundary: implementation-only, test required, no self-approval, submit to Tier3
```

Forbidden-path scan: **PASS**. `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative scan evidence only and was not used as a source; `.openclaw\skills` is non-authoritative scan evidence only and was not used as a source; `C:\Users\GHC\.agents` is non-authoritative scan evidence only and was not used as a source; `.codex\memories` is non-authoritative scan evidence only and was not used as a source.

## Measurement Contract

- Machine: Windows 10 `10.0.19044-SP0`, Intel `Family 6 Model 151`.
- Python: `3.14.4`; psutil: `7.2.2`.
- Dataset: `data/market_2015_now.parquet`.
- Date window: `2015-01-01` through `2026-06-13`.
- Universe: 30 highest-volume tickers selected by `profile_bottlenecks.py`.
- Workload: full data load, universe selection, panel preparation, 203-column feature generation, train/prediction lag computation.
- Configuration: `use_arsenal=True`, `use_alt_features=True`, `use_alt_data=True`, `use_llm_synth=False`.
- Seed: no stochastic operation in the measured profiling workload; fixed dataset/date/config/machine.
- PIT: profiling-only path; no feature/label/split or production trading behavior changed. Existing T-1/chronological behavior preserved.
- Measurement: subprocess wall clock plus process-tree peak RSS. Exactly 1 warm-up plus 3 measured runs. `--no-cprofile` removes profiler overhead from timing; hotspot ranking comes from the separate successful cProfile run.

## Verification

Compile command:

```text
python -m py_compile scripts/profile_bottlenecks.py scripts/measure_perf_baseline.py
```

Result: PASS, exit `0`.

Full-workload command:

```text
python scripts/measure_perf_baseline.py --script scripts/profile_bottlenecks.py --output .ly_state/session/gp_gate1_full_workload_baseline.json --output-dir .ly_state/session/gp_gate1_full_workload_runs -- --end-date 2026-06-13 --top 10 --no-cprofile --summary-output .ly_state/session/gp_gate1_bottlenecks.json
```

Result: PASS, exit `0`. Machine-readable artifacts:

- `.ly_state/session/gp_gate1_full_workload_baseline.json`
- `.ly_state/session/gp_gate1_full_workload_runs/run_01.log` through `run_04.log`
- `.ly_state/session/gp_gate1_bottlenecks.json`

## Full-Workload Baseline: 1 + 3

| Phase | Run | Wall-clock | Max RSS |
|---|---:|---:|---:|
| Warm-up | 1 | not measured by contract | log persisted |
| Measured | 1 | 27.6392 s | 1724.84 MB |
| Measured | 2 | 25.8017 s | 1711.55 MB |
| Measured | 3 | 25.7190 s | 1731.09 MB |
| **Median / max** | **3 measured** | **25.8017 s** | **1731.09 MB** |

The table is actual full-workload execution, not wrapper help or CLI smoke output.

## Hotspot Ranking

Separate cProfile command, rerun after the measurement-only command so it restored `profile_top`:

```text
python scripts/profile_bottlenecks.py --end-date 2026-06-13 --top 10 --profile-output .ly_state/session/gp_gate1_bottlenecks.prof --summary-output .ly_state/session/gp_gate1_bottlenecks.json
```

Top cumulative hotspots from the persisted `.prof`; `profile_top` in the persisted JSON contains the same ordering and cumulative values:

| Rank | Function | Cumulative |
|---:|---|---:|
| 1 | `UnifiedFeatureAdapter.generate_all` | `33.793s` |
| 2 | `AlternativeDataFetcher.generate_all` | `21.676s` |
| 3 | `AlternativeDataFetcher._derive_sentiment_indicators` | `21.392s` |
| 4 | `vsi_engine.calculate_sentiment` | `17.351s` |
| 5 | `vsi_engine._calculate_sentiment_frame` | `14.285s` |
| 6 | `arsenal.compute_ultimate_alphas` | `10.521s` |
| 7 | `vsi_engine._resolve_source_weights` | `7.895s` |

Profile workload evidence: `1,771,502` input rows, `30` tickers, `80,539` feature rows, `203` feature columns. The persisted `.prof` recorded `59,387,111` total calls (`58,310,158` primitive) in `41.415516s`; the JSON `profile_top` is non-empty and begins with the same 10 cumulative entries. This is hotspot evidence, not the timing baseline.

Evidence consistency check:

```text
python -m py_compile scripts/profile_bottlenecks.py scripts/measure_perf_baseline.py
Result: PASS, exit 0

python -c "import json,pstats; from pathlib import Path; j=json.loads(Path('.ly_state/session/gp_gate1_bottlenecks.json').read_text()); s=pstats.Stats('.ly_state/session/gp_gate1_bottlenecks.prof'); print('profile_top_non_empty=', bool(j['profile_top'].strip())); print('json_calls=', j['profile_top'].split('function calls')[0].strip()); print('prof_total_calls=', s.total_calls); print('prof_primitive_calls=', s.prim_calls); print('profile_runtime_seconds=', s.total_tt)"
profile_top_non_empty= True
json_calls= 59387111
prof_total_calls= 59387111
prof_primitive_calls= 58310158
profile_runtime_seconds= 41.41551569999948
Result: PASS, exit 0
```

## Minimal Remediation

- `scripts/profile_bottlenecks.py`: cProfile output regenerated after the measurement-only run had overwritten `profile_top` with an empty string; no production behavior changed.
- `scripts/measure_perf_baseline.py`: existing `1 + 3` measurement artifact retained; no production behavior changed.

No production optimization, PIT boundary, dataset, seed/config, or evolution behavior changed. No unrelated harness rewrite performed.

## Reproducibility Notes

- Run from repo root: `C:\Users\GHC\repos\OMEGA_QUANT`.
- Use the exact command above, fixed `--end-date 2026-06-13`, default dataset, same Python executable, same machine.
- `--no-cprofile` is required for stable timing; cProfile output is collected separately because profiler overhead materially inflates full-workload wall clock. The cProfile command must run after the timing command when both write `gp_gate1_bottlenecks.json`.
- Warm-up is executed and logged as `run_01.log`; measured runs are `run_02.log` through `run_04.log` internally, reported as measured 1 through 3.
- RSS is process-tree peak RSS, protecting measurement against child-process memory omission.

## Gate Statement

Gate 1 evidence consistency blocker **resolved**: valid full-workload benchmark remains persisted with exactly 1 warm-up plus 3 measured runs, median wall-clock, maximum RSS, and exact commands; regenerated `.prof` and `.json` now share call count, runtime, and hotspot ordering, with non-empty `profile_top`.

## L2 Boundary

Implementation and measurement evidence only. No audit, approval, or Tier 3 verdict issued.
