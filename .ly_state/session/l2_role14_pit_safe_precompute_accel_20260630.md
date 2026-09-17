# L2 Report: HYBRID_REGIME_PIT_SAFE_PRECOMPUTE_ACCEL_20260630

## Role / Gate
- role_id: 14
- role_name: `data-scientist`
- tier: L2 OpenCode
- gate: `HYBRID_REGIME_PIT_SAFE_PRECOMPUTE_ACCEL_20260630`

## Repo-Local Files Read
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
- `.gemini/antigravity-ide/scratch/ag-kit` -> not present
- `.openclaw/skills` -> not present
- `.codex/memories` -> not present
- `C:\Users\GHC\.agents` -> present, scanned as non-authoritative only, not used for role/skill loading

## Scope Changed
- `scripts/backtest_hybrid_regime.py`
- `tests/phase35/test_hybrid_regime_memory_optim.py`

## Problem
- parallel fold path still used process backend (`loky`) -> each worker could duplicate `feat_df`, `pred_lag_df`, `close_pivot_full`
- current shared precomputes existed in-memory only -> no reusable p2full cache boundary documented on disk
- peak memory stayed elevated even though some precompute was already PIT-safe
- L3 remediation finding: cache key could reuse stale p2full precomputes when `alpha_*` / `close` values changed but schema/shape/date bounds stayed identical

## PIT / Cache Classification
- fold-invariant + PIT-safe:
- `pred_lag_df = groupby(symbol)[alpha_*].shift(1)` over full panel, used for prediction only
- `close_pivot_full = pivot(date, symbol, close)` used only as source for per-fold train-date slicing in HMM fit
- fold-dependent:
- `train_feat`, train-local alpha lag block, IC ranking, regime-specific Ridge/LightGBM fits
- PIT-sensitive, must remain inside fold:
- HMM fit params
- GMM fit params
- regime-specific/global blend models
- any train-stat-derived feature selection / IC ranking / model outputs

## Implementation
- switched multi-worker execution from `joblib` `loky` to `threading`
- result: workers share one in-process copy of `feat_df`, `pred_lag_df`, `close_pivot_full` instead of process duplication
- kept fold-trained GMM/HMM/composite blending inside `train_fold_models()` unchanged
- added p2full-scoped reusable disk cache for only two safe intermediates:
- `data/cache/hybrid_regime_backtest/pred_lag_<cache_key>.pkl`
- `data/cache/hybrid_regime_backtest/close_pivot_<cache_key>.pkl`
- metadata file:
- `data/cache/hybrid_regime_backtest/meta_<cache_key>.json`
- cache enable rule: `"p2full" in output_tag.lower()` unless `OMEGA_DISABLE_P2FULL_PRECOMPUTE_CACHE=1`
- cache key now also includes a deterministic content fingerprint over sorted `date`, `symbol`, `close`, `alpha_*` values
- metadata now persists the same `content_fingerprint` for auditability
- released `raw_df` + `panel_full` before fold execution to lower resident memory before worker fan-out

## Remediation
- strengthened `build_precompute_cache_key()` with `build_precompute_content_fingerprint(feat_df)`
- fingerprint scope kept minimal + PIT-safe: sorted full-panel `date`, `symbol`, `close`, `alpha_*`
- unchanged boundary: cache still stores only `pred_lag_df` and `close_pivot_full`
- no fold-trained model, train-local stat, IC ranking, or composite prediction persisted globally
- added regression test mutating one `close` + one `alpha_one` value while keeping args/schema/shape/date bounds/symbol count identical
- expected result proven: 2nd load uses a different cache key, reports `cache_hit=False`, returns recomputed frames matching the mutated panel

## Exact Cache Boundary
- cached:
- full-panel alpha prediction lags via backward-only `shift(1)` per symbol
- full-panel close pivot for train-date slicing
- not cached:
- any fold-specific train slice
- any fold-trained HMM/GMM/model object
- any train-date alpha IC ranking or selected alpha subset
- any composite signal predictions persisted across folds

## Why PIT-Safe
- `pred_lag_df` uses only `T-1` history per symbol; no forward reference
- `close_pivot_full` is raw close reshaping only; fold training still slices by `train_dates` before HMM fit
- no global precompute of train-local stats/models; train-derived artifacts stay inside fold

## Verification Commands
```powershell
python -m py_compile "scripts/backtest_hybrid_regime.py" "tests/phase35/test_hybrid_regime_memory_optim.py"
pytest tests/phase35/test_hybrid_regime_memory_optim.py -q
```

## Verification Evidence
- `py_compile` -> pass
- `pytest tests/phase35/test_hybrid_regime_memory_optim.py -q` -> `6 passed`
- focused reduced-run equivalence test added:
- cached p2full precompute path equals uncached `precompute_prediction_lags()` output
- cached p2full precompute path equals uncached `precompute_close_pivot()` output
- 2nd load hits cache and returns identical frames
- stale-cache invalidation regression added:
- changed `alpha_*` / `close` values under identical metadata produce different cache keys
- mutated panel does not reuse prior disk cache (`cache_hit=False`)
- recomputed outputs equal fresh uncached outputs for mutated panel and differ from original cached outputs
- parallel path test updated to assert `threading` backend and serial/parallel aggregate equality

## Produced Files
- source/test updates only in this session:
- `scripts/backtest_hybrid_regime.py`
- `tests/phase35/test_hybrid_regime_memory_optim.py`
- runtime cache files are produced only when running p2full-tagged commands:
- `data/cache/hybrid_regime_backtest/pred_lag_<cache_key>.pkl`
- `data/cache/hybrid_regime_backtest/close_pivot_<cache_key>.pkl`
- `data/cache/hybrid_regime_backtest/meta_<cache_key>.json`

## Suggested p2full Runtime Command
```powershell
python scripts/backtest_hybrid_regime.py --start-date 2015-01-01 --end-date 2026-12-31 --folds 10 --n-test-folds 2 --embargo-pct 0.025 --label-horizon 60 --symbol-count 60 --workers 4 --cost-per-trade-bps 15 --top-k 7 --output-tag p2full_20260630_cache_smoke
```

## Notes
- no broad generalization beyond p2full cache gate
- no global-precompute of fold-trained or train-stat-dependent artifacts
- no audit/approval performed
