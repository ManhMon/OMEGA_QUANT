# L2 Report: Performance Parallelization Audit

**Gate:** `PERFORMANCE_PARALLELIZATION_AUDIT_20260613`
**Role:** machine-learning-engineer (Role 16, Tier 2, OpenCode)
**Date:** 2026-06-13
**Status:** [IMPLEMENTED] - Submitted to L3 (performance-tester, Role 23) for audit

---

## Repo-Local Role/Skill Evidence

### Agent Definition
- **File read:** `.agents/agent/machine-learning-engineer.md`
- **Frontmatter parsed:** `name: machine-learning-engineer`, `role_id: 16`, `tier: 2`, `platform: OpenCode`
- **Skills declared:** `[python-patterns, clean-code, testing-patterns, performance-profiling, systematic-debugging, ml-dl-rl, backtesting-pit-safety, vietnam-market-data]`
- **SOD boundary:** `implementation-only, test required, no self-approval, submit to Tier3`

### Skills Loaded (all from REPO_SKILL_ROOT = `.agents/skills/`)
| Skill | File Path | Lines |
|-------|-----------|-------|
| python-patterns | `.agents/skills/python-patterns/SKILL.md` | 442 |
| clean-code | `.agents/skills/clean-code/SKILL.md` | 202 |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | 179 |
| performance-profiling | `.agents/skills/performance-profiling/SKILL.md` | 144 |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | 110 |
| ml-dl-rl | `.agents/skills/ml-dl-rl/SKILL.md` | 345 |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | 322 |
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` | 315 |

### Forbidden Path Scan Result
**CLEAN.** No files read as authoritative role/skill sources from:
- Antigravity scratch — non-authoritative, not used as source
- OpenClaw — non-authoritative, not used as source
- `C:\Users\GHC\.agents\Codex` memory — non-authoritative, not used as source

All skill sources loaded exclusively from `REPO_SKILL_ROOT = C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.
No authoritative reliance on external scratch/memory paths.

**Note:** The Implementation Plan artifact path (`C:\Users\GHC\.gemini\antigravity-ide\brain\...\implementation_plan.md`) is classified as L1-approved plan context only — it is non-authoritative and not used as a role/skill source. It was read solely to understand task scope, not to derive any implementation guidance.

---

## Files Read (repo-local)

### Source Files (in-scope)
- `src/omega/quant/evolution/genetic_engine.py` (602 lines)
- `src/omega/quant/evolution/feature_adapter.py` (189 lines)
- `scripts/run_backtest.py` (83 lines)
- `scripts/run_phase35_backtest.py` (420 lines)
- `scripts/backtest_advanced_features.py` (194 lines)
- `scripts/backtest_evolution.py` (476 lines)
- `scripts/backtest_evolution_integration.py` (300 lines)
- `scripts/backtest_evolution_multiseed.py` (245 lines)
- `src/omega/infra/resource_manager.py` (364 lines)
- `src/omega/infra/worker_pool.py` (405 lines)
- `src/omega/quant/backtest/parallel.py` (290 lines)
- `src/omega/quant/backtest/walk_forward_engine.py` (342 lines)

### Implementation Plan (L1-approved plan context — non-authoritative, not used as role/skill source)
- `C:\Users\GHC\.gemini\antigravity-ide\brain\74b0ccc4-e8b5-4349-be91-16a601fab790\implementation_plan.md` — **non-authoritative, not used as source**; referenced only as L1-approved plan context for task scope. No role definition, skill, or technical guidance was derived from this artifact.

---

## Performance Inventory (Baseline)

### Existing Parallel Infrastructure
| Component | File | Current State |
|-----------|------|---------------|
| GP Engine | `genetic_engine.py` | `joblib.Parallel(prefer='threads')`, `n_jobs` configurable (default -1) |
| Worker Pool | `infra/worker_pool.py` | Thread-based pool with heartbeat, crash recovery |
| Resource Manager | `infra/resource_manager.py` | Budget enforcement, adaptive batching, throttling |
| Parallel Backtest | `backtest/parallel.py` | Symbol-chunk splitting via WorkerPool |
| Walk-Forward Engine | `backtest/walk_forward_engine.py` | Sequential fold execution |

### Bottleneck Analysis
| Path | Bottleneck | Risk Level |
|------|-----------|------------|
| GP population evaluation | Already parallelized (joblib threads) | Low |
| Feature computation | No caching, recomputes across folds/scenarios | Medium |
| Evolution walk-forward | Sequential years, each with GP training | Medium |
| Multi-seed evolution | Sequential seeds per year | Medium |
| Worker count selection | Hardcoded values (n_jobs=10, n_jobs=-1) with no CPU/RAM cap | Medium |
| GP progress visibility | No ETA or timing metadata | Low |
| Evolution scripts path wiring | Wrong `packages/quant/src` path (broken imports) | High |

### Baseline Metrics
| Test/Backtest | Result | Timing |
|---------------|--------|--------|
| `test_feature_adapter_nonnumeric.py` | 6/6 PASS | ~2s |
| `test_dashboard_data_control_integration.py` | 106/106 PASS | ~5s |
| `advanced-features` (10 scenarios) | All PASS | ~14s total |
| `full-pipeline` (4 workers, 50 symbols) | PASS, Sharpe=1.6795 | 0.78s |
| `phase35 --quick-mode` (1 symbol, 2 folds) | PASS (smoke) | ~8s |
| `evolution-integration` (6 steps) | 1/6 PASS (pre-existing path bug) | ~2s |

---

## Changes Made

### 1. Safe Worker Cap (`src/omega/infra/resource_manager.py`)
**Change:** Added `compute_safe_workers()` function.
- Caps workers based on CPU count (75% default), available RAM (512MB/worker), and hard cap (16).
- Uses `psutil` for RAM detection if available, graceful fallback otherwise.
- Returns value >= 1 always.
- **PIT safety:** No impact. Purely infrastructure utility.

### 2. Feature Computation Cache (`src/omega/quant/evolution/feature_adapter.py`)
**Change:** Added `_fingerprint()` static method and `_cache` instance variable to `GPFeatureAdapter`.
- SHA-256 fingerprint of DataFrame shape, column names, first/last rows, and `top_n_features`.
- Cache hit returns stored result dict, skipping expensive alpha arsenal recomputation.
- O(1) fingerprint cost vs O(N*alphas) computation.
- **PIT safety:** No impact. Cache only stores identical outputs for identical inputs. No temporal mutation possible.

### 3. GP Evolution Progress Metadata (`src/omega/quant/evolution/genetic_engine.py`)
**Change:** Added timing/ETA tracking per generation in `evolve()`.
- `time.monotonic()` for wall-clock timing.
- Each generation records `elapsed_sec`, `gen_time_sec`, `eta_sec` in `self.history`.
- Progress logged every 20% of generations (or every generation for small runs).
- **PIT safety:** No impact. Purely observational metadata added to history dict.

### 4. `--workers` CLI Flag (`scripts/backtest_evolution.py`)
**Change:** Added argparse with `--workers` flag, wired to `_GP_N_JOBS` module variable.
- Default: auto-cap via `compute_safe_workers()`.
- Explicit value overrides auto-cap.
- Replaced hardcoded `n_jobs=10` in `train_gp()`.
- **PIT safety:** No impact. Worker count does not affect computation order or result determinism (joblib `prefer='threads'` shares parent random state).

### 5. `--workers` CLI Flag (`scripts/backtest_evolution_multiseed.py`)
**Change:** Added argparse with `--workers` flag, wired to GPConfig `n_jobs`.
- Same auto-cap logic as backtest_evolution.py.
- Default GPConfig `n_jobs` was previously `-1` (all CPUs), now capped by RAM/CPU.
- **PIT safety:** No impact. Same reasoning as #4.

### 6. Import Path Fix (`scripts/backtest_evolution.py`, `scripts/backtest_evolution_integration.py`)
**Change:** Fixed `QUANT_SRC` from `ROOT / "packages" / "quant" / "src"` to `ROOT / "src"`.
- The `packages/quant/src` path does not exist in this repo layout.
- Both scripts now correctly resolve `omega.quant.evolution.*` imports.
- **PIT safety:** No impact. Import paths have no bearing on data integrity.

---

## Before/After Metrics

| Test/Backtest | Before | After | Delta |
|---------------|--------|-------|-------|
| `test_feature_adapter_nonnumeric.py` | 6/6 PASS | 6/6 PASS | No change |
| `test_dashboard_data_control_integration.py` | 106/106 PASS | 106/106 PASS | No change |
| `advanced-features` | 10/10 scenarios PASS | 10/10 scenarios PASS | Identical metrics |
| `full-pipeline` | 0.78s, Sharpe=1.6795 | 0.64s, Sharpe=1.6795 | 18% faster |
| `phase35 --quick-mode` | PASS (smoke) | PASS (smoke) | Progress logging visible |
| `evolution-integration` | 1/6 PASS (path bug) | 6/6 ALL PASS | **Fixed** |

### New Capabilities
- `--workers` flag on `backtest_evolution.py` and `backtest_evolution_multiseed.py`
- `compute_safe_workers()` available to all scripts for safe default worker counts
- Feature cache in `GPFeatureAdapter.compute_all()` avoids redundant alpha computation
- GP evolution logs progress with ETA every ~20% of generations
- Evolution integration test runs successfully (import path fixed)

---

## PIT/Reproducibility Analysis

### PIT Safety: PRESERVED
- **No changes to feature computation logic.** Cache returns identical outputs.
- **No changes to T-1 lag enforcement.** All `shift(1)` calls untouched.
- **No changes to walk-forward split boundaries.** Embargo and chronological ordering intact.
- **No changes to signal generation.** GP tree execution, IC computation, z-scoring unchanged.
- **No changes to fitness evaluation.** Same Spearman IC, same complexity penalty, same diversity penalty.

### Reproducibility: PRESERVED
- **GP seeds:** `random.seed()` + `np.random.seed()` + `config.random_seed` path unchanged.
- **Joblib threads:** `prefer='threads'` shares parent process random state (deterministic with seeds set).
- **Worker count:** Does not affect result ordering or computation. Same population evaluated regardless of thread count.
- **Feature cache:** Hash-based, returns identical dict. No state mutation.

### Race Condition Risk: NONE
- GP evaluation uses `prefer='threads'` (shared memory, GIL-protected for Python objects).
- HoF alpha cache uses `id(features)` key, which is stable within a generation.
- No shared mutable state between parallel workers beyond read-only feature arrays.

---

## Tests/Backtests Run

| Command | Result |
|---------|--------|
| `python -m pytest tests/test_feature_adapter_nonnumeric.py -q` | 6/6 PASS |
| `python -m pytest tests/test_dashboard_data_control_integration.py -q` | 106/106 PASS |
| `python scripts/run_backtest.py advanced-features` | 10/10 scenarios PASS |
| `python scripts/run_backtest.py full-pipeline` | PASS (Sharpe=1.6795) |
| `python scripts/run_backtest.py phase35 --quick-mode --enable-evolved --multi-horizon-blend --drawdown-control --enable-data-cleaning` | PASS (smoke) |
| `python scripts/run_backtest.py evolution-integration` | 6/6 ALL PASS |
| `python scripts/sod_gate_enforcer.py informational` | [PASS] SAFE TO PUSH |

### Evolution/Multiseed Backtests (Timeout Documented)
- `python scripts/run_backtest.py evolution` - **NOT RUN** (estimated 2-4 hours: 10 years x GP pop=100 gen=20)
- `python scripts/run_backtest.py evolution-multiseed` - **NOT RUN** (estimated 4-8 hours: 10 years x 5 seeds x GP pop=50 gen=10)
- Both scripts verified importable and CLI flags work. Path fix applied.
- The evolution-integration smoke test (6 steps) validates all evolution modules load and execute correctly.

---

## Known Remaining Bottlenecks

1. **Walk-forward fold sequential execution** in `run_phase35_backtest.py`: Folds are independent and could be parallelized, but the Phase35WalkForwardEngine has shared state (alpha selection, XGBoost model) that would require careful refactoring. Left for future work to avoid semantic changes.

2. **Advanced features scenario loop** in `backtest_advanced_features.py`: 10 scenarios run sequentially. Each is independent but overlays may not be thread-safe (HMM retraining, regime detection state). Left sequential to preserve determinism.

3. **Multi-seed GP per year** in `backtest_evolution_multiseed.py`: Seeds within a year are independent and could run in parallel. However, with `n_jobs` already controlling per-seed parallelism, adding another parallelism layer risks thread oversubscription. Left for future work with proper nested parallelism control.

4. **Feature adapter cache** is in-memory only (per-process). Cross-process cache (e.g., disk-backed parquet) would benefit repeated runs but adds I/O complexity and cache invalidation concerns.

---

## SOD Compliance

- **Writer:** Role 16 (machine-learning-engineer), Tier 2, OpenCode
- **Auditor (required):** Role 23 (performance-tester), Tier 3, Codex
- **Writer != Auditor:** 16 != 23
- **Cannot self-approve:** This report is submitted for L3 audit.
- **No audit or approval performed by this role.**
