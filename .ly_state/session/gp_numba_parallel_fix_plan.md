# Plan to Fix Parallel JIT VM Thread Safety and Lock Contention Bottlenecks

We identified two major performance and correctness bottlenecks in the GP evolution parallel backend (`threads`):
1. **Thread-Safety Stack Sharing**: The `context["stack"]` 2D array is shared across all concurrent threads, causing severe race conditions, numerical corruption, and cache line bouncing (false sharing/thrashing).
2. **Lock Contention**: The `_feature_cache_get` and `_feature_cache_set` helpers acquire a global cache lock `_FEATURE_LOCK_CACHE_GUARD` on every single node evaluation, completely serializing execution on a single core.

---

## Proposed Changes

### [MODIFY] [scripts/genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py)

#### 1. Implement Thread-Local VM Stacks
- Add thread-local storage (`threading.local()`) to manage VM stacks per thread.
- Dynamically allocate and cache `thread_stack` of shape `(MAX_VM_STACK_DEPTH, row_count)` per thread.
- Modify `_execute_tree` to fetch the thread-local stack and pass it into `_numba_execute_rpn` instead of reusing the shared `context["stack"]`.

#### 2. Implement Lock-Free Cache Helpers
- Remove locking from `_feature_cache_get` and `_feature_cache_set`.
- Utilize atomic dict operations in Python (`dict.get` and `dict.setdefault`) to implement lock-free cache access, relying on CPython's GIL for atomic thread safety.

### [MODIFY] [tests/quant_test_genetic_engine_optimizations.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/quant_test_genetic_engine_optimizations.py)

#### 3. Add Thread-Safety & Parallel Parity Regression Tests
- Create a unit test `test_gp_numba_parallel_eval_thread_safety` that spawns multiple concurrent threads executing `_execute_tree` on random individual trees.
- Verify that parallel outputs are mathematically identical to sequential execution outputs.
- Verify that concurrent executions do not corrupt each other's state or results.

---

## Verification Plan

### Automated Tests
- Run tests: `pytest tests/quant_test_genetic_engine_optimizations.py`
- Run JIT VM tests: `pytest tests/test_gp_numba_jit_vm.py`

### Benchmark Verification
- Execute the evolution benchmark:
  `python scripts/benchmark_v4_advanced.py --population-size 100 --workers 10 --backend threads`
- Expected:
  - Benchmark completes successfully with all 5 generations.
  - CPU usage shows multi-core scaling (utilizing all 10 threads).
  - Wall-clock runtime under 3 minutes.
  - Memory consumption stays under 4GB.
