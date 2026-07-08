# L2 Implementation Report — GP_ALT_DATA_FETCHER_OPTIMIZATION

**Role**: 15 data-engineer (Tier 2, OpenCode)
**Gate**: GP_ALT_DATA_FETCHER_OPTIMIZATION
**Date**: 2026-07-08
**SoD boundary**: implementation-only, test required, no self-approval, submit to Tier3

## Task
Implement the AlternativeDataFetcher MultiIndex restoration fix per
`.ly_state/session/gp_alternative_data_fetcher_index_restore_plan.md`.

## Root Cause (per plan + verification)
`AlternativeDataFetcher.generate_all()` reorders the input MultiIndex to
`['symbol', 'date']` (GP_ALT_DATA_FETCHER_OPTIMIZATION memory optimization for
contiguous `groupby(level='symbol')`) but never restores the original level
order before returning. Downstream `unified_feature_adapter.py` expects
`['date', 'symbol']`, so the swapped level order caused a silent
date<->symbol column swap — a dangerous correctness bug, not just a cosmetic
index ordering issue.

## Change
**File**: `src/omega/quant/evolution/alternative_data_fetcher.py`

Before return in `generate_all()` (line ~237):
```python
result = panel.join(features)
logger.info("Generated 10 alternative data signals")
return result
```

After:
```python
result = panel.join(features)

# Restore index levels order to prevent silent column swap in unified_feature_adapter.py
result = result.reorder_levels(['date', 'symbol']).sort_index()

logger.info("Generated 10 alternative data signals")
return result
```

The internal `[symbol, date]` reorder at the top of `generate_all()` is kept
(optimization preserved); only the *returned* frame is restored to
`['date', 'symbol']` and sorted. No change to PIT-safe internal logic.

## Tests
**File**: `tests/test_focal_point_detector.py`
Added regression test `test_generate_all_restores_date_symbol_index_order`
asserting:
- returned index level names == `['date', 'symbol']`
- index is monotonic increasing (sorted)
- a date slice contains exactly the expected symbols (catches swap)

Existing tests `test_alternative_data_fetcher_integration` and
`test_vectorized_date_mapping_equivalence` still pass (they use `.xs(level="date")`,
which is order-agnostic, so they did not catch the bug).

**Result**: `python -m pytest tests/test_focal_point_detector.py -q` → 6 passed.

## PIT Safety
Unchanged. `reorder_levels`/`sort_index` are pure index reshuffles; no
look-ahead, no future data introduced. Sentiment indicators still use T-1 lag.

## Repo-Local Files Read
- `.agents/agent/data-engineer.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.ly_state/session/gp_alternative_data_fetcher_index_restore_plan.md`
- `src/omega/quant/evolution/alternative_data_fetcher.py`
- `tests/test_focal_point_detector.py`

## Forbidden Path Scan
Scanned for reliance on non-authoritative sources:
`.gemini/antigravity-ide/scratch/ag-kit`, `.openclaw/skills`,
`C:\Users\GHC\.agents`, `.codex/memories`.
**Result**: NONE. All role/skill sources loaded exclusively from
`REPO_AGENT_ROOT` (`.agents/agent/`) and `REPO_SKILL_ROOT` (`.agents/skills/`).
No Antigravity scratch / OpenClaw / Codex-memory skill was read or relied upon.

## Submission
Ready for Tier 3 (Codex) independent audit. Do not self-approve.
