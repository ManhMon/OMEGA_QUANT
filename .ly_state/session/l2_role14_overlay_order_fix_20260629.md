# L2 Report: overlay_order_fix_20260629

- Role: `14 data-scientist`
- Tier: `2`
- Platform: `OpenCode`
- Gate: `HYBRID_REGIME_OVERLAY_ORDER_FIX_20260629`
- Scope: `scripts/backtest_hybrid_regime.py`, `.ly_state/session/l2_role14_overlay_order_fix_20260629.md`
- Status: `IMPLEMENTED_AND_TESTED`

## Repo-Local Role/Skill Source Evidence

First repo-local role file read per skill source contract:

- `.agents/agent/data-scientist.md`

Parsed frontmatter evidence:

- `name: data-scientist`
- `role_id: 14`
- `tier: 2`
- `platform: OpenCode`
- `skills: [python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow]`

Exact repo-local skill files read from declared `skills` frontmatter only:

- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

Lesson 1 applied:

- L2 report lists exact repo-local role/skill source loading evidence.

## Forbidden Path Scan Result

Forbidden paths are non-authoritative. Presence on disk does not permit authoritative loading.

- `.gemini\antigravity-ide\scratch\ag-kit` -> `False` (`non-authoritative`, not read, not used as source)
- `.openclaw\skills` -> `False` (`non-authoritative`, not read, not used as source)
- `C:\Users\GHC\.agents` -> `True` (`non-authoritative`, exists on disk, not read, not used as source)
- `.codex\memories` -> `False` (`non-authoritative`, not read, not used as source)

Result:

- Repo-local role/skill loading only.
- No authoritative reliance on forbidden paths.
- Scratch/OpenClaw/global Codex memory sources remain forbidden for this task.

## Change Applied

Updated `build_scenario_overlays()` in `scripts/backtest_hybrid_regime.py`.

Overlay order updated in both scenario stacks:

- `WeightSmoothingOverlay(ema_alpha=0.08)` now runs before `LongOnlyConcentratedOverlay(top_k=top_k)`
- `LongOnlyConcentratedOverlay(top_k=top_k)` now runs before `RiskSizingOverlay(...)`

Scoped line evidence:

- `scripts/backtest_hybrid_regime.py:494-588`
- `scripts/backtest_hybrid_regime.py:530-540` (`Baseline` order)
- `scripts/backtest_hybrid_regime.py:566-583` (`Hybrid` order)

Diff summary within scope:

- `Baseline`: `WeightSmoothingOverlay` -> `LongOnlyConcentratedOverlay` -> `RiskSizingOverlay`
- `Hybrid`: `WeightSmoothingOverlay` -> `LongOnlyConcentratedOverlay` -> `RiskSizingOverlay`

## Verification

Command run:

```powershell
pytest
```

Result:

- `2433 passed, 12 skipped, 738 warnings`
- Pytest status: `GREEN`

## Notes

- Repo-relative paths used in report body.
- No files outside declared scope edited in this pass.
- No audit/approval performed.
