# Plan to Implement Candidate-Level Parallelization in Batch JIT Kernels

We identified that OLS neutralization (`_numba_batch_ridge_neutralize`) and Daily IC computation (`_numba_batch_daily_ics`) are executed sequentially on a single thread. To fully utilize hardware CPU cores and achieve the benchmark target of under 3 minutes, we will enable Numba's candidate-level automatic parallelization.

---

## Proposed Changes

### [MODIFY] [scripts/genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py)

#### 1. Parallelize OLS Neutralization Batch Kernel with Thread-Safe Scratch Buffers
- Add `parallel=True` to the JIT decorator for `_numba_batch_ridge_neutralize`.
- Replace the candidate loop `for candidate_idx in range(candidate_count):` with `for candidate_idx in prange(candidate_count):` using `numba.prange`.
- **Thread-Safety Check (L3 Requirement)**: Allocate the scratch buffers `row_buffer`, `gram`, `rhs`, and `beta` (originally allocated outside the loop) **inside** the `prange` candidate loop body. This ensures that each concurrent thread gets private copies of these mutable buffers, preventing data races.
- Read-only structures (like `shared_gram` and `base_row_buffer`) will remain outside the loop since they are read-only.

#### 2. Parallelize Daily ICs Batch Kernel
- Add `parallel=True` to the JIT decorator for `_numba_batch_daily_ics`.
- Replace the candidate loop `for candidate_idx in range(candidate_count):` with `for candidate_idx in prange(candidate_count):` using `numba.prange`.

### [MODIFY] [tests/quant_test_genetic_engine_optimizations.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/quant_test_genetic_engine_optimizations.py)

#### 3. Update / Add Parity Tests
- Ensure that the new JIT parallelized kernels compile successfully.
- Verify that parallel JIT outputs are mathematically identical to the single-threaded baseline outputs.

---

## Verification Plan

### Automated Tests
- Run tests: `pytest tests/quant_test_genetic_engine_optimizations.py`
- Run JIT VM tests: `pytest tests/test_gp_numba_jit_vm.py`

### Benchmark Verification
- Execute:
  `python scripts/benchmark_v4_advanced.py --population-size 100 --workers 10 --backend threads`
- Expected:
  - CPU usage scales across multiple cores (utilizing all 10 cores).
  - Wall-clock runtime under 3 minutes for all 5 generations.
  - Memory consumption remains under 4GB.
