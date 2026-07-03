# L2 Report — BACKTEST_REPORT_AUTO_GENERATION_20260627

## Role
- role_id: 14
- role_name: `data-scientist`
- tier: 2
- platform: `OpenCode`
- sod_boundary: `implementation-only, test required, no self-approval, submit to Tier3`

## Scope
- Added `scripts/generate_report.py`
- Modified `scripts/run_backtest.py`

## Repo-Local Skill Sources Read
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

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit`: not used as source
- `.openclaw\skills`: not used as source
- `C:\Users\GHC\.agents`: not used as source
- `.codex\memories`: not used as source

## Implementation
- Added JSON-to-Markdown report generator reading `data/phase35_results/hybrid_regime_cpcv_comparison.json` and writing `data/phase35_results/backtest_report.md`.
- Report includes metadata, config, aggregate Baseline vs Hybrid comparison, hybrid profitability summary, alpha IC by regime, runtime.
- Updated `scripts/run_backtest.py` to call `scripts/generate_report.py` only when backtest exit code is `0` and mode is `hybrid-regime`.

## PIT / Research Safety
- Change is reporting-only; no model logic, data timestamps, CV splits, or signal generation changed.
- Existing PIT behavior in backtest pipeline remains untouched.

## Verification
- Syntax check: `python -m py_compile scripts/run_backtest.py scripts/generate_report.py`
- Generator run: `python scripts/generate_report.py`
- Output confirmed: `data/phase35_results/backtest_report.md`

## Notes
- Repo-local `checklist.py` and `verify_all.py` were not present in workspace search, so they were not runnable.
- No audit performed. Tier 3 review required.
