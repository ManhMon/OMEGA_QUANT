# HYBRID_REGIME_P2FULL_NARROW_SWEEP_EXEC_PILOT_20260630

Status: EXECUTED_FAILED

Gate: `HYBRID_REGIME_P2FULL_NARROW_SWEEP_EXEC_PILOT_20260630`

## 1. Exact Repo-Local Files Read

- `.agents/agent/data-scientist.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- `.ly_state/session/l2_role14_p2full_narrow_sweep_plan_20260630.md`
- `scripts/backtest_hybrid_regime.py`

## 2. Forbidden Path Scan Result

Checked non-authoritative paths:

- `C:/Users/GHC/.agents` -> present, non-authoritative, not used as source
- `C:/Users/GHC/.claude` -> present, non-authoritative, not used as source
- `C:/Users/GHC/repos/OMEGA_QUANT/Codex memory` -> not present
- `C:/Users/GHC/repos/OMEGA_QUANT/OpenClaw` -> not present
- `C:/Users/GHC/repos/OMEGA_QUANT/Antigravity scratch` -> not present

Result: no forbidden path used as authoritative source.

## 3. Approved Pilot Executed

Approved candidate: `Experiment C1` from `.ly_state/session/l2_role14_p2full_narrow_sweep_plan_20260630.md`

Plan command used `--workers 0`; per task instruction this execution used native worker flag `--workers 8` and no other scope expansion.

Exact command run:

```powershell
python scripts/backtest_hybrid_regime.py --start-date 2015-01-01 --end-date 2026-12-31 --folds 10 --n-test-folds 2 --embargo-pct 0.025 --label-horizon 60 --symbol-count 60 --workers 8 --cost-per-trade-bps 15 --top-k 7 --rebalance-every-n-days 10 --output-tag p2full_20260630_c1_rebal10_tcost15
```

## 4. Execution Timing

- Start timestamp: `2026-06-30T07:56:24.6968005+07:00`
- End timestamp: `2026-06-30T07:56:53.8917581+07:00`
- Wall-clock runtime: `29.190 sec`
- Exit code: `1`

## 5. Stdout/Stderr Summary

Observed startup/summary lines:

- Loaded data: `1776593` rows, `703` tickers, date range `2015-01-05` to `2026-06-26`
- Dynamic universe: `137` rebalance dates, avg `55.7` symbols/rebalance
- CPCV execution entered parallel mode with `8` workers

Terminal failure:

```text
numpy._core._exceptions._ArrayMemoryError: Unable allocate 258. MiB array shape (190, 355351) data type float32
```

Interpretation:

- Pilot did start
- Pilot did not complete fold aggregation
- Failure occurred under the required `--workers 8` setting during parallel fold execution

## 6. Output Artifacts

Expected output JSON path:

- `data/phase35_results/hybrid_regime_cpcv_comparison_p2full_20260630_c1_rebal10_tcost15.json`

Artifact result:

- Output JSON not produced

Observed file scan:

- No files matched `data/phase35_results/*p2full_20260630_c1_rebal10_tcost15*.json`

## 7. Key Result Metrics

No final result metrics available because the run terminated before `aggregate_fold_results()` / `save_comparison_json()` completed.

Available execution metrics only:

- `workers`: `8`
- `runtime_sec`: `29.190`
- `exit_code`: `1`
- `status`: `failed_pre_output`

## 8. Scope Compliance

- Ran only approved pilot `C1`
- Used repo-relative paths from `REPO_ROOT`
- Did not modify production source code
- Wrote only this L2 execution report in `.ly_state/session/`
- Stopped after pilot execution attempt and report write
