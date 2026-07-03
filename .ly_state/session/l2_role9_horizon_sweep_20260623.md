# L2 Report - LABEL_HORIZON_SWEEP_ENSEMBLE_20260623

Role: 9 backend-engineer
Session ID: l2_role9_horizon_sweep_20260623
Date: 2026-06-23
Status: completed

## Scope

- `scripts/sweep_label_horizons.py`
- `scripts/run_backtest.py`
- `tests/test_horizon_sweep.py`
- `data/horizon_sweep_results/horizon_sweep_20260623.md`
- `data/horizon_sweep_results/horizon_sweep_20260623.json`

## Repo-Local Skill Source Evidence

Authoritative files read:

- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`

Forbidden path scan result:

- No authoritative role/skill loading from `.gemini\antigravity-ide\scratch\ag-kit`
- No authoritative role/skill loading from `.openclaw\skills`
- No authoritative role/skill loading from `C:\Users\GHC\.agents`
- No authoritative role/skill loading from `.codex\memories`

## Implementation

### `scripts/sweep_label_horizons.py`

- Kept sequential horizon sweep over `[10, 15, 20, 30, 40, 60, 90]`
- Calls `scripts/run_backtest.py hybrid-regime --quick-mode --workers 1 --label-horizon <H> --output-tag horizon_<H>`
- Computes `tc_drag = gross_return - mean_return`
- Writes aggregate outputs to:
  - `data/horizon_sweep_results/horizon_sweep_20260623.json`
  - `data/horizon_sweep_results/horizon_sweep_20260623.md`
- Added `--resume` to reuse completed per-horizon JSONs and finish interrupted sweeps without rerunning prior horizons

### `scripts/run_backtest.py`

- Added `enforce_worker_safety()`
- For `hybrid-regime` with `--label-horizon`:
  - appends `--workers 1` if omitted
  - exits with error if `--workers` is not `1`
- Result: serial-only safety enforced at wrapper level, not just sweep caller level

### `tests/test_horizon_sweep.py`

- Verified command construction
- Verified serial-only worker guard
- Verified `tc_drag` computation
- Verified subprocess/result loading path
- Verified markdown/json artifact writing
- Verified default dry-run sweep
- Verified resume mode skips subprocess when per-horizon JSON exists
- Verified `run_backtest.py` wrapper appends/rejects worker settings correctly

## Verification Run

Commands executed:

- `pytest tests/test_horizon_sweep.py`
- `pytest tests/test_horizon_sweep.py tests/test_strict_repo_local_skill_loading.py`
- `pytest`
- `python scripts/sweep_label_horizons.py --workers 1`
- `python scripts/sweep_label_horizons.py --workers 1 --resume`

Results:

- `pytest tests/test_horizon_sweep.py` -> pass (`9 passed`)
- `pytest tests/test_horizon_sweep.py tests/test_strict_repo_local_skill_loading.py` -> pass (`95 passed`)
- `pytest` -> exit code `0`
- Sweep completed and wrote both final artifacts

Warnings observed:

- Pytest cache warning on `.pytest_cache\v\cache` creation conflict
- Existing deprecation/update warnings from SQLAlchemy/vnai during test and backtest runs

## Sweep Output Summary

Artifact: `data/horizon_sweep_results/horizon_sweep_20260623.md`

| Horizon | Status | Scenario | Sharpe | Gross | Net | TC Drag | Max DD | Folds |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 10 | ok | Hybrid | -1.3996 | 61.21% | -26.67% | 87.89% | -28.52% | 5 |
| 15 | ok | Hybrid | -1.2366 | 38.38% | -25.01% | 63.39% | -27.18% | 5 |
| 20 | ok | Hybrid | -1.5419 | 55.25% | -28.76% | 84.01% | -30.22% | 5 |
| 30 | ok | Hybrid | -1.3197 | 41.58% | -24.86% | 66.44% | -26.49% | 5 |
| 40 | ok | Hybrid | -1.3804 | 25.24% | -29.49% | 54.73% | -30.99% | 5 |
| 60 | ok | Hybrid | -1.3124 | 51.11% | -26.81% | 77.92% | -28.55% | 5 |
| 90 | ok | Hybrid | -1.4993 | 68.51% | -29.36% | 97.87% | -32.10% | 5 |

Quick read:

- Best mean Sharpe in sweep: horizon `15` (`-1.2366`)
- Best mean return in sweep: horizon `30` (`-24.86%`)
- Lowest TC drag in sweep: horizon `40` (`54.73%`)
- All 7 horizons completed with `n_folds_completed = 5`, `n_folds_errored = 0`

## Notes

- First full sweep run exceeded tool timeout after producing horizon artifacts through `40`; `--resume` was added to finish `60` and `90` without rerunning completed horizons.
- Worktree contains many unrelated untracked backtest artifacts outside this scoped change; none were reverted or modified intentionally.
