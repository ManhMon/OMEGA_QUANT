# L2 Report: Hybrid Regime Horizon Tuning

**Gate:** `HYBRID_REGIME_HORIZON_TUNING_20260624`
**Role:** `14 data-scientist`
**Platform:** `OpenCode`
**Date:** `2026-06-24`
**Status:** COMPLETE - default horizon updated, requested backtests executed, results recorded

---

## 1. Provenance

### Role Spec Read
- `.agents/agent/data-scientist.md` - READ OK

### Skills Read (repo-local only)
- `.agents/skills/python-patterns/SKILL.md` - READ OK
- `.agents/skills/clean-code/SKILL.md` - READ OK
- `.agents/skills/testing-patterns/SKILL.md` - READ OK
- `.agents/skills/systematic-debugging/SKILL.md` - READ OK
- `.agents/skills/performance-profiling/SKILL.md` - READ OK
- `.agents/skills/quant-research/SKILL.md` - READ OK
- `.agents/skills/vietnam-market-data/SKILL.md` - READ OK
- `.agents/skills/backtesting-pit-safety/SKILL.md` - READ OK
- `.agents/skills/data-science-workflow/SKILL.md` - READ OK

### Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` - NOT PRESENT under `REPO_ROOT`; not accessed
- `.openclaw\skills` - NOT PRESENT under `REPO_ROOT`; not accessed
- `C:\Users\GHC\.agents` - EXISTS outside repo but not accessed as authoritative source
- `.codex\memories` - NOT PRESENT under `REPO_ROOT`; not accessed

**Verdict:** repo-local skill source contract satisfied. Only files under `REPO_AGENT_ROOT` and `REPO_SKILL_ROOT` were used as authoritative sources.

---

## 2. Scope

- In-scope file: `scripts/backtest_hybrid_regime.py`
- Requested change: set default `--label-horizon` to `60`
- Requested execution: full CPCV backtest, `2020-01-01` to `2026-06-18`, capital `2,000,000,000`, dynamic universe, 4 workers

---

## 3. Code Change

### File Modified
- `scripts/backtest_hybrid_regime.py:130-131`

### Exact Change
- `--label-horizon` default changed from `5` -> `60`
- help text changed from `default: 5` -> `default: 60`

### Notes
- Worktree already contained unrelated pre-existing modifications in `scripts/backtest_hybrid_regime.py` before/alongside this task.
- This task's direct source edit was limited to the default horizon lines above.

---

## 4. Verification

### Syntax / CLI
- `python -m py_compile "scripts/backtest_hybrid_regime.py"` - PASS
- `python "scripts/backtest_hybrid_regime.py" --help` - PASS
- Verified help now shows `CPCV label horizon in bars (default: 60)`

### Repo-Required Validation Scripts
- `python "checklist.py"` - NOT RUNNABLE; file not found at repo root
- `python "verify_all.py"` - NOT RUNNABLE; file not found at repo root
- `glob("**/checklist.py")` - no matches under `REPO_ROOT`
- `glob("**/verify_all.py")` - no matches under `REPO_ROOT`

---

## 5. Requested Backtest Run

### Command
```powershell
python "scripts/backtest_hybrid_regime.py" --start-date 2020-01-01 --end-date 2026-06-18 --capital 2000000000 --folds 10 --n-test-folds 2 --dynamic-universe --workers 4 --output-tag horizon60_20260624
```

### Output Artifact
- `data/phase35_results/hybrid_regime_cpcv_comparison_horizon60_20260624.json`

### Runtime
- `977.3s` (`16.3 min`)

### Config Confirmed in JSON
- `start_date`: `2020-01-01`
- `end_date`: `2026-06-18`
- `capital`: `2000000000.0`
- `folds`: `10`
- `n_test_folds`: `2`
- `label_horizon`: `60`
- `dynamic_universe`: `true`
- `workers`: `4`

### Aggregate Results
| Scenario | Mean Sharpe | Std Sharpe | Mean Return | Mean MaxDD | Folds |
|----------|-------------|------------|-------------|------------|-------|
| Baseline | `-1.0381` | `0.5668` | `-14.26%` | `-18.67%` | `45` |
| Hybrid | `-0.7522` | `0.5952` | `-3.49%` | `-5.85%` | `45` |

### Profitability Diagnostics
| Scenario | Gross Ret | TC | Cash Days | TO Avg | Expo Avg | IC |
|----------|-----------|----|-----------|--------|----------|----|
| Baseline | `+27.29%` | `41.55%` | `76.3%` | `0.2444` | `0.2858` | `0.0298` |
| Hybrid | `+2.44%` | `5.93%` | `93.5%` | `0.0419` | `0.0574` | `0.0298` |

### Regime Diagnostics
- `alpha_ic_per_regime`: Bull=`NaN`, Sideways=`NaN`, Bear=`+0.0298`
- `n_bull=0`, `n_sideways=0`, `n_bear=45` for both scenarios

---

## 6. Control Comparison: Horizon 5

Because the task goal said "de cai thien Sharpe Ratio", a control run with the previous explicit horizon was executed to measure actual impact.

### Control Command
```powershell
python "scripts/backtest_hybrid_regime.py" --start-date 2020-01-01 --end-date 2026-06-18 --capital 2000000000 --folds 10 --n-test-folds 2 --dynamic-universe --workers 4 --label-horizon 5 --output-tag horizon5_control_20260624
```

### Control Output Artifact
- `data/phase35_results/hybrid_regime_cpcv_comparison_horizon5_control_20260624.json`

### Control Runtime
- `984.3s` (`16.4 min`)

### Control Aggregate Results
| Scenario | Mean Sharpe | Std Sharpe | Mean Return | Mean MaxDD | Folds |
|----------|-------------|------------|-------------|------------|-------|
| Baseline | `-1.2258` | `0.6441` | `-14.08%` | `-17.10%` | `45` |
| Hybrid | `-0.7258` | `0.6732` | `-3.02%` | `-5.99%` | `45` |

### Delta: Horizon 60 minus Horizon 5
| Scenario | Delta Mean Sharpe | Delta Mean Return | Delta Mean MaxDD |
|----------|-------------------|-------------------|------------------|
| Baseline | `+0.1877` | `-0.18%` | `-1.57%` |
| Hybrid | `-0.0264` | `-0.47%` | `+0.14%` |

### Interpretation
- For **Hybrid** (target strategy), `label_horizon=60` did **not** improve Sharpe vs `label_horizon=5`
- Hybrid mean Sharpe worsened: `-0.7258` -> `-0.7522`
- Hybrid mean return worsened: `-3.02%` -> `-3.49%`
- Hybrid mean max drawdown improved slightly: `-5.99%` -> `-5.85%`
- For **Baseline**, Sharpe improved, but task objective was Hybrid strategy improvement

---

## 7. PIT / Backtest Integrity Notes

- Used existing CPCV path in `scripts/backtest_hybrid_regime.py`
- JSON confirms `label_horizon=60` was propagated into the run config
- Dynamic universe enabled as requested
- Full combinatorial fold count completed: `45/45`
- No fold errors recorded

---

## 8. Deliverables

- Source update: `scripts/backtest_hybrid_regime.py`
- Backtest artifact: `data/phase35_results/hybrid_regime_cpcv_comparison_horizon60_20260624.json`
- Control artifact: `data/phase35_results/hybrid_regime_cpcv_comparison_horizon5_control_20260624.json`
- This report: `.ly_state/session/l2_role14_horizon_tuning_20260624.md`

---

## 9. Final Status

Implementation complete.

Requested default updated to `60`.

Requested full backtest executed successfully.

Measured outcome: **Hybrid Sharpe did not improve** versus horizon `5` control under the same backtest settings.
