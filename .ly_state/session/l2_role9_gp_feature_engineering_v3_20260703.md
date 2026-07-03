# L2 Report: GP Feature Engineering V3

## Repo-Local Files Read
- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `scripts/genetic_alpha_evolution_v3.py`
- `src/omega/quant/evolution/genetic_engine.py`
- `tests/quant_test_genetic_engine.py`

## Forbidden Path Scan Result
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
- `.openclaw\skills` is non-authoritative and not used as source.
- `C:\Users\GHC\.agents` is non-authoritative and not used as source.
- `.codex\memories` is non-authoritative and not used as source.

## Changes Implemented
- `scripts/genetic_alpha_evolution_v3.py`
- Removed raw OHLC terminals from `FEATURE_COLS`; terminal set now: `returns_1d`, `returns_5d`, `vol_ratio`, `hl_range`, `oc_range`, `hl_range_cs_z`, `oc_range_cs_z`.
- Added `hl_range_cs_z` and `oc_range_cs_z` in `load_dataset()` via per-date cross-sectional z-score.
- Added volume-quartile sector proxy `__sector__` via per-date `pd.qcut(..., 4, labels=False)` on ranked volume, then shifted by ticker for PIT safety.
- Added metadata passthrough keys `__date__`, `__log_market_cap__`, and `__sector__` to train/test feature dicts.
- Set GP config flags: `use_time_fold_ir=True`, `time_folds=3`, `neutralize_size_sector=True`, `use_icir=False`.
- `src/omega/quant/evolution/genetic_engine.py`
- Verified terminal exclusion path already ignores `__*` keys: `self.feature_names = [k for k in features.keys() if not k.startswith('target') and not k.startswith('__')]`.
- Added `GPConfig` fields: `neutralize_size_sector`, `use_time_fold_ir`, `time_folds`, `fold_ir_std_floor`.
- Replaced neutralization helper with `_neutralize_cross_section(alpha_arr, log_mcap_arr, sector_arr, date_arr) -> residuals`, using per-date `np.linalg.lstsq` on intercept + `__log_market_cap__` + sector dummies (3 cols max after dummy drop), rank-deficiency guarded.
- Added tiny-residual zeroing (`abs(x) < 1e-12 -> 0.0`) after regression to avoid false rank correlation from floating-point noise.
- Added `_compute_time_fold_ir(...)` with chronological date folds via `np.array_split(sorted_unique_dates, config.time_folds)`, minimum 2 valid folds, IR denominator floored by `fold_ir_std_floor`.
- Updated `_compute_combined_ic()` and `_compute_time_fold_ir()` to pass `__sector__` into neutralization.
- Updated `evolve()` to disable random 100k row subsampling when `use_time_fold_ir=True`.
- `tests/quant_test_genetic_engine.py`
- Added `test_time_fold_ir_stable_alpha_beats_spike`.
- Added `test_sector_neutralization_removes_sector_effect`.

## Test Results
- `python -m py_compile "scripts\genetic_alpha_evolution_v3.py" "src\omega\quant\evolution\genetic_engine.py" "tests\quant_test_genetic_engine.py"` -> PASS
- `pytest "tests\quant_test_genetic_engine.py" -q` -> PASS (`10 passed`)

## Scope Verification
- Top-level pre-existing dirty worktree was stashed with `git stash push -u -m "l2-scope-proof-preexisting" -- . ":(exclude)scripts/genetic_alpha_evolution_v3.py" ":(exclude)src/omega/quant/evolution/genetic_engine.py" ":(exclude)tests/quant_test_genetic_engine.py"`.
- Nested repo dirt under `.agents/skills/improve` was also stashed with `git -C ".agents/skills/improve" stash push -u -m "l2-scope-proof-nested-improve"` because that embedded repo made top-level `git diff --name-only` show an out-of-scope path.
- `git diff --name-only` after stash isolation ->
  - `scripts/genetic_alpha_evolution_v3.py`
  - `src/omega/quant/evolution/genetic_engine.py`
  - `tests/quant_test_genetic_engine.py`
- Stash restoration queued after verification: top-level `git stash pop`, nested `.agents/skills/improve` `git stash pop`.
