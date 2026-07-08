# L2 Report — role 15 data-engineer — GP Weekly Evolution Alt Concat Optimization

- **Role**: 15 data-engineer (OpenCode L2 Implementation)
- **Gate**: GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION
- **Session ID**: l2_role15_gp_weekly_evolution_alt_concat_optimization_20260708
- **Date**: 2026-07-08
- **Tier**: L2 (implementation only — no audit, no approval)

## Repo-Local Files Read:
- .agents/agent/data-engineer.md
- .agents/skills/python-patterns/SKILL.md
- .agents/skills/database-design/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/systematic-debugging/SKILL.md
- .agents/skills/performance-profiling/SKILL.md
- .agents/skills/vietnam-market-data/SKILL.md
- .agents/skills/data-science-workflow/SKILL.md

Forbidden path scan: confirmed non-authoritative and not used as source for .gemini\antigravity-ide\scratch\ag-kit, .openclaw\skills, C:\Users\GHC\.agents, .codex\memories.

## Scope

1. `scripts/run_weekly_evolution.py` — `_generate_alternative_features`: merge alt_features_df + alt_data_features_df into `combined_alt` first via outer join, then a single left merge onto result. Empty-frame guards via `pd.DataFrame()` defaults.
2. `src/omega/quant/evolution/alternative_data_fetcher.py` — `_derive_sentiment_indicators`: narrow copy `panel_fp` to `['foreign_flow','liquidity_shock','sector_rotation']`, pre-group that for the focal-point detector. Original `panel` untouched for `daily_returns` / `daily_foreign`.

## Changes

### `scripts/run_weekly_evolution.py`

- Initialized `alt_features_df = pd.DataFrame()` and `alt_data_features_df = pd.DataFrame()` before their try/blocks so the merge step has concrete (possibly empty) frames even when a generator raises.
- Moved both `result.merge(...)` calls out of their respective try/blocks into a single guarded block:
  ```python
  if not alt_features_df.empty or not alt_data_features_df.empty:
      combined_alt = alt_features_df.merge(alt_data_features_df, on=["date", "ticker"], how="outer")
      result = result.merge(combined_alt, on=["date", "ticker"], how="left")
  ```
- Halves merge passes over `result` (was 2 sequential merges, now 1).
- Empty-frame guard: if both generators fail, `combined_alt` is empty DataFrame and the merge is skipped via the outer `if`, preserving prior `result` shape.

### `src/omega/quant/evolution/alternative_data_fetcher.py`

- Before pre-grouping `panel` by date for `market_by_date`, build `panel_fp = panel[['foreign_flow','liquidity_shock','sector_rotation']].copy()` (intersected with existing columns).
- `market_by_date` now iterates `panel_fp.groupby(level='date')`, so the dict holds narrow slices (3 cols vs full feature set).
- Original `panel` is preserved for the downstream `daily_returns = panel.groupby(level='symbol')['close'].pct_change().groupby(level='date').mean()` and `daily_foreign = panel['margin_proxy'].groupby(level='date').mean()` calls.

### `src/omega/quant/sentiment/focal_point_detector.py`

- No changes. The detector already accepts a pre-sliced single-index DataFrame (`market_panel.index.nlevels == 1` branch). The narrow `panel_fp` slices satisfy that path.

## Tests

```
python -m pytest tests/test_genetic_alpha_evolution_v4.py tests/test_focal_point_detector.py --tb=short
============================== 24 passed, 5 warnings in 6.31s ==============================
```

Relevant cases verified:
- `test_generate_alternative_features_preserves_rows_and_adds_alt_columns` — stubs both generators; asserts rows preserved and both `alt_stub_feat` + `alt_stub_data` columns added. Passes (covers new outer-merge happy path with both frames populated).
- `test_generate_alternative_features_raises_on_duplicate_keys` — duplicate (date, ticker) still raises. Passes.
- `test_alternative_data_fetcher_integration` — full `generate_all()` path, including `_derive_sentiment_indicators` via the narrow `panel_fp`. Passes (validates end-to-end PIT T-1 lag semantics survive the narrow copy).
- `test_generate_all_restores_date_symbol_index_order` — index reordering not regressed. Passes.
- V4 JIT / time-fold / neutralization parity tests still pass.

## PIT Safety

- T-1 lag still applied by caller of `_generate_alternative_features` (unchanged).
- `_derive_sentiment_indicators` still uses `prev_date_str = dates[i-1]` to compute T-1-derived news items. Narrow copy preserves `panel`'s chronological content; `daily_returns` and `daily_foreign` still derive from full `panel` (uses `close` and `margin_proxy` which are not in `panel_fp`).
- Focal point detector reads only `foreign_flow`, `liquidity_shock`, `sector_rotation` via its `KEYWORD_MAPPINGS.market_indicator` — all present in `panel_fp`.

## SOD Boundary

- L2 implementation only. No audit, no approval. Submitting to L3 for independent review.
