# Role 23 - Performance Impact Assessment

**Scope**
Read-only assessment. No files modified.

**Verdict: [NEEDS_FIX]**

Plan is structurally reasonable, but performance controls are under-specified. Combined L4 audit lists “performance benchmarks before/after” as low priority; Role 23 escalates this to a gate requirement before Phase 1.

**Evidence**
Current hot path:
[ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3541) defines `compute_ultimate_alphas`.
[alpha_factory.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/alpha_factory.py:10) imports it eagerly.
[quant_engine.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/quant_engine.py:44) imports `alpha_factory` eagerly.
[pipeline_factory.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/pipeline_factory.py:8) imports walk-forward/pipeline classes eagerly.

Measured with `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=src`:
- `omega.quant.ultimate_alpha_arsenal` cold import: `16.12s`, `205.7MB` peak traced alloc.
- `omega.quant.alpha_factory` cold import: `13.67s`, `205.8MB`.
- `omega.quant.quant_engine` cold import: `13.78s`, `206.6MB`.
- `compute_ultimate_alphas` synthetic 2,600 rows/all groups: `2.232s`, `132 alpha_ cols`, `18.6MB` compute peak.
- same data, `alpha_groups=['momentum']`: `0.191s`, `17 alpha_ cols`, `3.0MB` compute peak.

**1. Import Performance**
Splitting 200KB into 16 modules is not the main risk. Python loading 16 small files adds minor overhead versus current cold-import side effects.

Main risk: eager exports. If `ultimate_alpha_arsenal.py` wrapper or `alpha/__init__.py` imports all 16 modules at top level, import time likely stays bad or gets slightly worse.

Current import is dominated by side effects:
[ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:88) tries `omega.core.memory.resource_monitor`; missing submodule triggers `omega.core.__init__`, which eagerly imports broad packages. That pulls `omega.data`, `vnstock`, and governance validation side effects. `omega.data.__init__` eagerly imports `vnstock_*` modules at [omega/data/__init__.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/__init__.py:80). Governance import prints validation output via [validate_ly_state.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/governance/validate_ly_state.py:24).

Requirement: Phase 0/1 must eliminate import-time side effects and use lazy category loading.

**2. Computation Performance**
Splitting files should not change alpha speed if formulas remain identical. The current function is serial: `alpha_groups=None` becomes `all_groups` at [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3592), then category blocks run sequentially from [line 3601](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3601).

There is existing partial group gating, but tail calls always run:
- `compute_vn_alphas` at [line 3940](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3940)
- `compute_promoted_alphas` at [line 3957](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3957)

So even `alpha_groups=['momentum']` still touches VN/promoted code. Fix before claiming lazy/group perf gains.

**3. Memory Impact**
More modules add small module-object overhead. Real memory risk is eager imports plus DataFrame intermediates.

Current compute stores Series in `alphas_dict`, then single `pd.concat` at [line 3936](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3936). That is good for fragmentation, but peak memory scales with `rows * alpha_count`. Repeated `df.copy()`/`sort_values()` inside many alpha functions is likely the larger compute-memory cost.

**4. Pipeline Performance**
`QuantEngine.run` calls `_discover_alphas`, which calls `compute_core_alphas` and then full arsenal by default at [quant_engine.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/quant_engine.py:332). Pipeline runtime itself will not materially change from file moves unless import paths become eager or duplicate modules are merged incorrectly.

`PipelineFactory` cold import is also heavy because it imports backtest/walk-forward stacks at module import time. Refactor should defer heavy imports until `create(mode=...)`.

**5. Required Benchmarks Before Restructure**
Gate must record baseline and post-change:
- Cold import time/RSS: `ultimate_alpha_arsenal`, `alpha_factory`, `quant_engine`, `pipeline_factory`.
- Warm import time in same process.
- Alpha compute: all groups, each group, and `alpha_groups=['momentum']`.
- Real panel benchmark: current production/backtest feature panel, fixed dates/tickers.
- Synthetic benchmark: 10 tickers x 260 business days, plus larger 200 tickers x 1,250 days.
- Output equality: same alpha columns, same row order, `np.allclose(equal_nan=True)` for all alpha columns.
- Pipeline smoke: `QuantEngine.run` on fixed fixture, `PipelineFactory.create/run` for backtest/walk-forward.
- Memory: peak RSS/tracemalloc, import stdout/stderr side effects.

Acceptance thresholds:
- Full alpha compute wall time: no worse than `+10%`.
- Peak memory: no worse than `+15%`.
- Cold import: no worse than baseline; target improvement after lazy loading.
- Selected group compute: must not import/compute unrelated groups.
- Zero import-time print/log side effects from package import.

**6. Optimization Opportunities**
- Replace `omega.core.memory.resource_monitor` import with a local lightweight fallback or lazy import.
- Make `alpha/__init__.py` lazy via `__getattr__`; do not `import *` all category modules.
- Move category imports inside a registry: `group -> loader -> compute`.
- Only call VN/promoted alphas when their group is requested.
- Share sorted DataFrame/groupby context across alpha functions.
- Fuse multi-period rolling calculations where possible.
- Keep symbol-chunking from `alpha_factory_optimized.py`; do not chunk by time/fold because it breaks rolling windows.
- Consider parallel by symbol/category only after benchmark; default serial is safer for memory.

**Final**
[NEEDS_FIX] until Phase 0/1 adds explicit lazy-import design, benchmark gates, and import-side-effect cleanup. Splitting into 16 modules is acceptable only if wrappers remain backward compatible without eager-loading the full arsenal.

