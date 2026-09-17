# Codex Gate 7 Plan Final Review v3

**Review target**: `.ly_state/session/gate7_neutralization_liquidity_plan.md`
**Date**: 2026-07-04
**Auditor**: Codex L3
**Role**: 23 `performance-tester`
**Verdict**: [NEEDS_REVISION]

## Repo-Local Sources Read

- `.agents/AGENTS.md`
- `.agents/agent/performance-tester.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/webapp-testing/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`

Forbidden-path reliance: none. No production code or tests modified.

## Required Checks

1. Required working directory command was run:
   `Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'`

2. Current plan file was read:
   `.ly_state/session/gate7_neutralization_liquidity_plan.md`

3. Required grep was run:
   `rg -n "ticker\.str|str\[0\]" .ly_state/session/gate7_neutralization_liquidity_plan.md`

   Result: no matches. `rg` exited `1`, which is expected for no matches.

## Findings

### 1. Unsafe sector fallback removed: PASS

No `ticker.str` or `str[0]` fallback remains in the current plan. The previous v2 blocker is resolved.

### 2. Phase 2 reconcile approach is still internally inconsistent: BLOCKING

The top-level Phase 2 direction now correctly says to reconcile with existing Gates 2-3 infrastructure:

- Existing `_volume_quartile_sector_proxy()` is named as the active sector proxy.
- Existing `__sector__` and `__log_market_cap__` metadata are reused.
- Existing `_neutralize_cross_section()`, `_batch_neutralize_cross_section()`, and `_build_neutralization_cache()` are named.
- The plan explicitly says not to add `_residualize_size_sector()`.

However, later code blocks still use `_residualize_size_sector()`:

- Neutralization test snippet calls `_residualize_size_sector()` for alpha and target.
- Validation helper snippet calls `_residualize_size_sector()` for signal and target.

This directly contradicts the stated "do not add parallel helper" contract. L2 could implement or test against a duplicate/nonexistent helper.

Required revision:

- Replace all `_residualize_size_sector()` references with the existing extended neutralization path, or explicitly define them as pseudocode aliases that must not be implemented.

### 3. Sector source still conflicts with reconcile plan: BLOCKING

The plan says sector is a volume-quartile proxy and `sector_mapping_level2.csv` is not used. Later sections still say:

- `sector` mapped from static file.
- `data/sector_mapping_level2.csv` should be verified or created.

That conflicts with the RECONCILE approach and reopens the old "sector mapping provenance" path.

Required revision:

- Remove static sector file references from PIT checklist and file list, or explicitly mark them out of scope/not used for Gate 7.

### 4. Phase 4 liquidity filter is not sound as written: BLOCKING

The implementation block is mostly correct:

- Uses `traded_value = close * volume`.
- Computes rolling mean per ticker.
- Shifts by ticker after rolling.
- Adds centralized `_evaluation_mask()`.
- Requires raw validation ranking replacement.

But the earlier Solution snippet still shows:

```python
avg_volume_20d = df.groupby("ticker")["volume"].rolling(20).mean().shift(1)
liquidity_mask = avg_volume_20d > min_avg_volume
```

This is the unsafe/ambiguous version from prior review: raw share volume despite VND threshold semantics, plus a global shift risk after grouped rolling materialization.

Also, the metadata section says include train/val/oos/lockbox, but the code block only shows train/test.

Required revision:

- Replace the Solution snippet with the traded-value, ticker-local shift implementation.
- Show all four metadata assignments: train, val, oos, lockbox.

### 5. K=3 fix is explicit: PASS

The plan explicitly documents the current `time_folds=8` bug and required `time_folds=3` fix. This check passes.

## Verdict Rationale

The literal unsafe `ticker.str[0]` fallback is gone and the main Phase 2/4 intent is much improved. The plan is still not L2-ready because stale code snippets contradict the reconcile approach and the Phase 4 solution block preserves an unsafe liquidity calculation pattern. These are plan-level blockers because L2 could implement those sections literally.

## Required Actions

1. Delete or rewrite all `_residualize_size_sector()` snippets to use the existing neutralization infrastructure.
2. Remove `sector_mapping_level2.csv` / static sector mapping references from this Gate 7 plan unless explicitly out of scope.
3. Replace the raw-volume/global-shift liquidity Solution snippet with the traded-value/ticker-local shift implementation.
4. Show `__liquidity_mask__` assignment for train, validation, OOS, and lockbox features.

## Final Verdict

[NEEDS_REVISION]
