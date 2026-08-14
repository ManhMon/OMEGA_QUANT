# Deep Performance and Logic Audit - GP System

**Date:** 2026-07-14  
**Auditor:** Codex L3  
**Verdict:** [NEEDS_FIX] for production-grade GP promotion  
**Scope:** `src/omega/quant/evolution/`, GP scripts under `scripts/`, `src/omega/quant/alpha/vn.py`

## Sources Read

- `.agents/AGENTS.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `src/omega/quant/evolution/genetic_engine.py`
- `src/omega/quant/evolution/diverse_alpha_evolution.py`
- `src/omega/quant/evolution/genetic_alpha.py`
- `src/omega/quant/evolution/genetic_programming.py`
- `src/omega/quant/evolution/fitness.py`
- `src/omega/quant/evolution/continuous_learning.py`
- `scripts/run_weekly_evolution.py`
- `scripts/genetic_alpha_evolution_v4.py`
- `scripts/genetic_alpha_evolution_v3.py`
- `src/omega/quant/alpha/vn.py`

Forbidden/non-authoritative paths: `.codex/memories` was queried only for prior-context discovery and was not used as an authoritative role, skill, or audit source. No production source was edited.

## Executive Summary

The GP stack has useful recent optimization work, especially V4 RPN execution, daily IC vectorization, and batch neutralization. However, several core paths still have correctness and PIT risks:

1. Root subtree mutation/crossover can silently no-op.
2. Standard engine `cs_rank`/`cs_zscore` rank across the whole panel, not per date.
3. Fitness metrics are inconsistent across train, validation, promotion, and registry.
4. Turnover penalties are computed on flattened arrays, not ticker/date positions.
5. V4 has avoidable heap allocation, unbounded caches, and lock contention.
6. `vn.py` is PIT-safe only when the caller applies a later T-1 shift; the module itself does not enforce it for `compute_all_vn_alphas`.

## Blocking Findings

### 1. Root subtree replacement silently fails

**Severity:** Critical  
**Files:** `src/omega/quant/evolution/genetic_engine.py:725-743`, `1564-1585`; `src/omega/quant/evolution/genetic_programming.py:152-171`, `443-475`

`GPNode.replace_subtree()` only searches children. If `get_random_subtree()` returns the root, crossover/mutation does nothing. Root selection probability is non-trivial for small trees. This reduces effective mutation/crossover rates and biases evolution toward elite cloning.

Impact:

- `crossover()` can return unchanged `parent1`.
- `mutate()` can return unchanged individual.
- Effective exploration is lower than configured `crossover_rate`/`mutation_rate`.

Fix:

- Return a new root when `old is self`, or implement pure functional `replace_random_subtree(root, new_subtree) -> root`.
- Add a one-file assert test: force root selection, verify expression changes.

### 2. Legacy `Genome.mutate()` is random restart, not subtree mutation

**Severity:** High  
**File:** `src/omega/quant/evolution/genetic_alpha.py:196-204`

`Genome.mutate()` discards the whole tree and returns a new random tree. It does not replace a random subtree as the docstring says. Diverse evolution relies on this in seeded populations.

Impact:

- Mutation destroys useful building blocks.
- Island model becomes seed plus random restart, not gradual local search.
- Fitness progress has higher variance.

Fix:

- Implement real subtree replacement for `Node`.
- Keep a small probability for full random restart as a separate operator.

### 3. Legacy crossover only swaps `children[0]`

**Severity:** High  
**File:** `src/omega/quant/evolution/genetic_alpha.py:207-226`

The legacy `Genome.crossover()` deep-copies both parents but only replaces the first child of parent 1. It never selects arbitrary subtrees.

Impact:

- Right-side branches in binary expressions are under-explored.
- Unary root trees often barely change.
- Search diversity is much lower than implied by config.

Fix:

- Use random node path selection in both parents.
- Preserve `max_depth` with a post-crossover depth guard.

### 4. `cs_rank` and `cs_zscore` are global in standard engine

**Severity:** Critical PIT/logic risk  
**File:** `src/omega/quant/evolution/genetic_engine.py:547-563`, `1248-1277`

`_cs_rank()` and `_cs_zscore()` operate on the entire flattened vector. For a panel, this ranks rows across all dates. That is not a cross-section. It also lets a row at date T be transformed using observations from future dates.

V4 fixes this in the JIT path with date grouping (`scripts/genetic_alpha_evolution_v4.py:567-631`), but the base engine still exposes unsafe operators in default `GPConfig.unary_ops`.

Impact:

- Look-ahead bias when standard engine or fallback path uses these ops.
- Wrong economics: cross-sectional operators should be per date.

Fix:

- Remove `cs_rank`/`cs_zscore` from base `GPConfig.unary_ops` until a date-aware implementation is used.
- In `_execute_tree`, route these ops through `__date__` groups and fail closed if dates are missing.

### 5. Time-series operators are flat in `genetic_programming.py`

**Severity:** High PIT/logic risk  
**File:** `src/omega/quant/evolution/genetic_programming.py:342-355`, `569-590`

The legacy public API converts a MultiIndex panel to raw arrays, then rolling ops run over the flattened order. No ticker/date metadata is injected.

Impact:

- Rolling windows bleed between symbols.
- Panel ordering can change signal values.
- PIT claim in module header is not true for multi-symbol panels.

Fix:

- Deprecate this module or wrap it over `genetic_engine.py` grouped TS logic.
- If retained, require `__ticker__` and `__date__` and group all TS ops.

### 6. Turnover penalty is not position turnover

**Severity:** High  
**Files:** `src/omega/quant/evolution/genetic_engine.py:922-927`; `src/omega/quant/evolution/diverse_alpha_evolution.py:335-338`; `src/omega/quant/evolution/fitness.py:29-36`, `75-87`

The main engine computes `np.diff(np.sign(alpha_series))` over a flattened array. With data sorted by ticker/date, this includes ticker-boundary jumps and misses daily rebalance turnover across tickers.

Impact:

- Cost penalty is noisy and structurally wrong.
- Fitness can prefer alphas with low flat sign changes but high portfolio turnover.

Fix:

- Pivot signal by `date x ticker`.
- Compute turnover as mean absolute weight/position change per ticker per date.
- Apply liquidity mask before turnover, not after.

### 7. Train, validation, and promotion metrics are inconsistent

**Severity:** High  
**Files:** `scripts/run_weekly_evolution.py:1434-1445`, `1073-1159`; `src/omega/quant/evolution/continuous_learning.py:53-58`; `scripts/genetic_alpha_evolution_v3.py:168-221`

Training in V3/V4 uses daily cross-sectional IC or fold IR. Weekly validation culling uses global Spearman over all rows. Promotion uses `ContinuousLearningEngine.evaluate_model()`, which uses global Pearson correlation and a simplified unannualized Sharpe proxy.

Impact:

- An alpha can pass promotion while failing the actual train objective.
- Global row correlation overweights high-row regimes and ignores daily cross-section structure.
- Results are not comparable across stages.

Fix:

- Use one canonical scorer: daily cross-sectional Spearman IC, optional size/sector neutralization, liquidity mask, date-weighted aggregation.
- Replace `ContinuousLearningEngine.evaluate_model()` or do not use it for GP promotion.

### 8. Negative IC can be promoted in weekly path

**Severity:** High  
**File:** `scripts/run_weekly_evolution.py:1120-1128`

Promotion checks `abs(ic) > 0.05 and sharpe > 0.1`. If `ic` is negative but the simplified Sharpe is positive, the alpha can be promoted with the wrong direction.

Fix:

- Require signed `ic > threshold`.
- If short signals are allowed, explicitly flip the formula/sign before registration and record the transformation.

### 9. `vn.py` does not enforce T-1 lag for `compute_all_vn_alphas`

**Severity:** High if used directly  
**File:** `src/omega/quant/alpha/vn.py:20-277`

Most features include current-day OHLCV and same-date cross-sectional stats. Weekly caller applies T-1 lag later (`scripts/run_weekly_evolution.py:440-443`), so that path is mostly protected. The module itself does not enforce lag for `compute_all_vn_alphas`.

Impact:

- Any caller using `compute_all_vn_alphas()` directly as model features at date T gets same-day data.
- The name/comments imply PIT safety, but safety is external.

Fix:

- Add `lag: bool = True` default, grouped by ticker.
- Or rename to `compute_raw_vn_alphas()` and expose `compute_pit_vn_alphas()` that always shifts.
- Add an assert test: first row per ticker is NaN after PIT feature generation.

### 10. Weekly liquidity mask rolls across tickers and ignores CLI threshold

**Severity:** Medium/High  
**File:** `scripts/run_weekly_evolution.py:880-891`, `1024-1025`, `1090-1092`, `1422-1424`

`_inject_liquidity_mask()` computes rolling average over the flat frame, not per ticker. It also uses default `min_avg_volume=500000.0` because callers do not pass CLI `args.min_avg_volume`.

Impact:

- Liquidity eligibility bleeds across ticker boundaries.
- CLI threshold appears configurable but is ignored in GP feature dicts.

Fix:

- Use `df.groupby("ticker")["volume"].rolling(...)`.
- Pass `args.min_avg_volume` and `args.avg_volume_window` through every injection call.

## Performance Findings

### 11. V4 batch ridge neutralization allocates per date group

**Severity:** High performance  
**File:** `scripts/genetic_alpha_evolution_v4.py:690-789`

Inside `_numba_batch_ridge_neutralize()`, workspaces are allocated inside the date-group loop (`workspace_row_buffer`, `workspace_gram`, `workspace_rhs`, `workspace_beta` at lines `731-735`).

Impact:

- Repeated heap allocation inside a hot loop.
- Comment says "zero-allocation optimization", but implementation still allocates per date.

Fix:

- Allocate workspaces once outside the date loop.
- Or process candidates in fixed blocks and reuse buffers.

### 12. V4 rolling operators copy input on every call

**Severity:** Medium/High performance  
**File:** `scripts/genetic_alpha_evolution_v4.py:469-565`

Each Numba rolling function allocates `values = np.empty(x.size)` and copies `x`. Since VM stack already owns scratch arrays, this copy is avoidable.

Impact:

- Extra O(rows) allocation per rolling operator per candidate.
- Heap pressure increases with nested TS expressions.

Fix:

- Read `x` directly unless mutation aliasing is proven.
- If scratch is required, allocate one per thread and reuse it.

### 13. V4 cache growth is unbounded

**Severity:** Medium/High performance  
**File:** `scripts/genetic_alpha_evolution_v4.py:72-75`, `409-423`, `1606-1637`

`_GLOBAL_VM_PROGRAM_CACHE` has no eviction. Per-feature subtree cache stores arrays by `(fingerprint, expression)` and writes through a lock.

Impact:

- Long runs with many expressions can accumulate compiled RPN programs and signal arrays.
- Threaded evaluation contends on cache writes.

Fix:

- Put an LRU cap on global VM program cache.
- Avoid caching full subtree outputs for one-off full trees, or cap by memory.
- Prefer per-generation cache, then clear after generation.

### 14. Dense batch matrices multiply memory

**Severity:** Medium performance  
**File:** `scripts/genetic_alpha_evolution_v4.py:1747-1823`

Each batch creates `raw_alpha`, `processed_alpha`, and `neutralized_alpha` matrices. With `rows x batch_size` and float64, memory can spike quickly.

Fix:

- Keep `batch_fitness_size` conservative.
- Consider float32 for candidate matrices after numeric stability checks.
- Stream neutralization/scoring by smaller candidate blocks.

### 15. `loky` and multiprocessing are exposed for Windows despite large payloads

**Severity:** Medium performance  
**Files:** `scripts/run_weekly_evolution.py:59-87`, `1280-1292`; `src/omega/quant/evolution/diverse_alpha_evolution.py:99-118`, `460-477`

Windows worker count is capped, but `loky`/`multiprocessing` still serialize large feature dictionaries and genomes. Diverse mode defaults to `loky`.

Impact:

- Process spawn and pickle overhead can dominate GP evaluation.
- Numba monkey-patching state must exist in workers; fragile across spawn boundaries.

Fix:

- Default all GP scripts to threads on Windows.
- Only allow `loky` behind a measured benchmark flag.
- Use memmapped NumPy arrays if process backend is required.

## Algorithmic/Fitness Findings

### 16. V4 first-fold early rejection biases selection

**Severity:** Medium  
**File:** `scripts/genetic_alpha_evolution_v4.py:1221-1281`, `1460-1519`

Early rejection after fold 0 rejects non-audit candidates before later folds. This is a speed hack, not the same objective as full fold IR.

Impact:

- Alphas weak in early regime but robust later can be discarded.
- Fitness is partly path-dependent on fold order.

Fix:

- Use early rejection only in a coarse pre-screen.
- Re-score survivors and a deterministic audit sample with full folds every generation.
- Log reject counts and audit disagreement rate.

### 17. Fold IR uses fold means, not daily IC distribution

**Severity:** Medium  
**File:** `src/omega/quant/evolution/genetic_engine.py:338-415`

The engine computes mean daily IC per fold, then IR across fold means. With only 2-3 folds, the denominator is noisy and clipped to `[-2, 2]`.

Impact:

- Fitness is sensitive to arbitrary fold boundaries.
- `fold_ir_std_floor` can dominate small fold counts.

Fix:

- Use daily IC mean/std across all train dates for primary fitness.
- Keep fold stability as a penalty: `mean_daily_ic - lambda * std(fold_means)`.

### 18. V3/V4 hard-code stale dataset end date

**Severity:** Medium  
**Files:** `scripts/genetic_alpha_evolution_v3.py:127-134`; `scripts/genetic_alpha_evolution_v4.py:1586-1593`

Both scripts load data only through `2026-05-14`. Current audit date is `2026-07-14`.

Impact:

- Weekly evolution can silently ignore recent data.

Fix:

- Default `end_date=None` or latest available date.
- Log actual min/max dates after load.

### 19. `compute_hit_rate()` is not a portfolio hit rate

**Severity:** Medium  
**File:** `scripts/genetic_alpha_evolution_v3.py:204-208`; `src/omega/quant/evolution/diverse_alpha_evolution.py:335-338`

It compares row-level signal sign to forward-return sign. It ignores cross-sectional rank portfolio construction, neutrality, and costs.

Fix:

- Replace with top/bottom quantile long-short hit rate by date.
- Or remove from promotion gates.

## PIT Findings - `vn.py`

### Mostly PIT-safe when used by weekly caller

`compute_all_vn_alphas()` uses only current/past per-ticker rolling data plus same-date cross-sectional stats. In `run_weekly_evolution.prepare_features()`, all `FEATURE_COLUMNS` are shifted by ticker after VN alpha generation (`scripts/run_weekly_evolution.py:440-443`). That makes the weekly path mostly T-1 safe.

### Direct-use PIT hazard

The function itself returns unshifted features. Current-day inputs include:

- `volume`, `high`, `low`, `close`, `open` in many features (`src/omega/quant/alpha/vn.py:66-85`, `103-121`, `180-225`).
- same-date market return `_mkt_ret` (`src/omega/quant/alpha/vn.py:34-38`, `195-206`).
- same-date cross-sectional ranks (`src/omega/quant/alpha/vn.py:259-261`).

These are valid EOD features only if traded from T+1 or shifted before model use.

### Cross-sectional neutralization safety

Size/sector neutralization in the engine is per date (`src/omega/quant/evolution/genetic_engine.py:210-285`) and is PIT-safe with respect to time if `__log_market_cap__` and `__sector__` are already T-1 lagged. V3/V4 do shift these metadata in their dataset loaders (`scripts/genetic_alpha_evolution_v3.py:156-158`, `scripts/genetic_alpha_evolution_v4.py:1580-1582`). Weekly `_inject_private_gp_columns()` should be separately checked because it is not included in the snippets above, and promotion paths rebuild private metadata.

## Recommended Fix Order

1. Fix root replacement and legacy `Genome` subtree mutation/crossover.
2. Disable unsafe standard `cs_rank`/`cs_zscore` unless date-aware.
3. Replace weekly validation/promotion scoring with one canonical daily CS IC scorer.
4. Fix turnover to use date x ticker position changes.
5. Add PIT-safe wrapper/default lag to `vn.py`.
6. Fix `_inject_liquidity_mask()` grouping and CLI threshold propagation.
7. Cap V4 caches and move Numba workspace allocations out of date loops.
8. Default Windows GP parallelism to threads; require benchmark evidence for process backends.
9. Remove stale hard-coded script end dates.

## Minimal Test Plan

- Unit: root mutation/crossover changes root when selected.
- Unit: `cs_rank` ranks independently per date and cannot run without `__date__`.
- Unit: grouped TS rolling never uses values from another ticker.
- Unit: `compute_all_vn_alphas(lag=True)` first row per ticker is NaN or masked.
- Unit: `_inject_liquidity_mask()` rolling reset at ticker boundary.
- Integration: same candidate scored by train, val, promotion path returns same daily CS IC.
- Performance check: one generation V4 with `population_size=64`, compare allocations/time before and after workspace/cache fixes.

## Final Verdict

**[NEEDS_FIX]**

The system is close to usable for research iteration, but not safe for production alpha promotion until the crossover/mutation root bug, unsafe cross-sectional ops, metric inconsistency, and PIT wrapper gaps are fixed.
