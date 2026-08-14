# GP Performance Optimization Audit

**Role**: IT Systems Auditor (Role 25, Codex L3)
**Gate**: `gp_performance_optimization_audit`
**Date**: 2026-07-15
**Scope**: `src/omega/quant/evolution/genetic_engine.py`, `scripts/genetic_alpha_evolution_v4.py`, `scripts/run_weekly_evolution.py`

## Executive Finding

The Numba VM accelerates expression execution, not dominant end-to-end fitness work. At 2,000 candidates and 300,000 rows, one generation processes at least 600 million candidate-row values before folds, copies, neutralization, ranking, and secondary metrics. Approximately eight minutes per generation is consistent with memory-bandwidth pressure, repeated sorting, per-date solves, allocations, and orchestration outside the VM.

## Exact Root Causes

### 1. Static target ranking repeats

- `_numba_batch_daily_ics` parallelizes candidates (`scripts/genetic_alpha_evolution_v4.py:1182`).
- `_numba_daily_ics` allocates daily alpha and target arrays (`scripts/genetic_alpha_evolution_v4.py:1373`).
- Both arrays are ranked per candidate-date (`scripts/genetic_alpha_evolution_v4.py:1382`). Static target ranks repeat population-size times.
- Numba removes Python overhead, not `O(N log N)` sorting or allocation traffic.

### 2. Daily IC remains candidate-major

- Every worker traverses identical dates, target, indices, masks.
- Full `dates ? candidates` output is allocated then immediately reduced (`scripts/genetic_alpha_evolution_v4.py:1180`, `scripts/genetic_alpha_evolution_v4.py:1258`).

### 3. Neutralization repeats work

- Base path runs `np.linalg.lstsq` per date (`src/omega/quant/evolution/genetic_engine.py:312`).
- Fallback rebuilds Gram matrix, identity, solve per date (`scripts/genetic_alpha_evolution_v4.py:1157`).
- JIT batch path allocates candidate workspaces inside every date loop (`scripts/genetic_alpha_evolution_v4.py:731`).
- Static designs are not reduced to cached factorizations.

### 4. Batch matrices saturate memory bandwidth

- `column_stack` copies VM outputs (`scripts/genetic_alpha_evolution_v4.py:1763`).
- Post-processing creates clipped, standardized, mask, percentile, mean, standard-deviation intermediates (`scripts/genetic_alpha_evolution_v4.py:1014`).
- Neutralization copies again (`scripts/genetic_alpha_evolution_v4.py:1133`); fold slicing copies again (`scripts/genetic_alpha_evolution_v4.py:1226`).
- A 300,000 ? 32 float64 matrix is 76.8 MB. Concurrent intermediates reach hundreds of MB per batch, tens of GB traffic per generation.

### 5. Fold rejection occurs late

- Full fold batch IC runs before rejection (`scripts/genetic_alpha_evolution_v4.py:1251`).
- Rejected columns remain present for later fold processing.
- Base path slices every row-aligned feature per individual/fold (`src/omega/quant/evolution/genetic_engine.py:368`).

### 6. JIT and threading remain operational bottlenecks

- `cache=True` signatures compile lazily; no production-signature warm-up exists.
- Rank sort remains serial. Joblib, Numba, BLAS may oversubscribe.
- Batch joblib dispatch repeats (`scripts/genetic_alpha_evolution_v4.py:1754`). Islands execute sequentially (`scripts/genetic_alpha_evolution_v4.py:1892`).
- Broad exception fallback silently invokes scalar evaluation (`scripts/genetic_alpha_evolution_v4.py:1820`).

### 7. Secondary metrics repeat scans

- SciPy `spearmanr` and `rankdata` remain in diversity/orthogonalization (`src/omega/quant/evolution/genetic_engine.py:965`, `src/omega/quant/evolution/genetic_engine.py:994`, `src/omega/quant/evolution/genetic_engine.py:1012`).

## Concrete Optimization Strategy

### Priority 0: Stage instrumentation

1. Time VM, post-process, neutralization, fold preparation, daily ranking, IC reduction, diversity, orchestration separately.
2. Record candidates/second, bytes allocated, peak RSS, compilation time, Numba signatures, rejection counts, scalar-fallback count.
3. Log batch fallback exception class and batch ID; never silently accept scalar fallback in performance runs.

### Priority 1: Pre-rank static targets

1. Cache per dataset/fold: compact valid indices, daily target ranks, centered ranks, sum-of-squares, valid counts.
2. Rank only alpha values. Compute Pearson against cached target ranks.
3. Use a fast path for fully finite candidate columns. Use masked fallback only for candidate-specific NaNs.
4. Accumulate `sum_ic` and `count_ic` directly; remove the full daily-IC output matrix unless diagnostics request it.

Expected result: removes one sort, target gather, and target allocation per candidate-date.

### Priority 2: Date-major vectorized daily IC

1. Process one date across a candidate tile.
2. Rank candidate columns in a compiled kernel; reuse pre-ranked target.
3. Center ranks and compute correlations with column reductions or matrix multiplication.
4. Tile candidates from a memory budget, not fixed batch size. Benchmark 8, 16, 32.
5. Avoid rows-by-candidates masks when target/liquidity validity is shared.

### Priority 3: Pre-factor neutralization

1. Precompute per-date valid indices and design matrix.
2. Precompute Cholesky of `X'X + ?I`; use QR fallback where required.
3. Solve batched RHS `X' A`, then residualize `A -= X B`.
4. Allocate workspaces once outside date loops or in thread-local maximum-sized buffers.
5. Pre-neutralize static target once per fold/dataset, keyed by target, fold, mask, design fingerprint.

Expected result: removes repeated Gram construction and candidate-local solves.

### Priority 4: Reduce copies and dtype width

1. Keep VM/tile intermediates float32 where parity permits; accumulate OLS/correlation in float64.
2. Winsorize, standardize, neutralize in one reusable tile buffer.
3. Pass precomputed fold indices into JIT kernels; avoid materialized fold matrices.
4. Reuse raw buffer after each stage when prior representation is no longer needed.
5. Replace per-candidate `dict(features)` with explicit candidate metadata arguments.

### Priority 5: Compile and control parallelism

1. Warm every production kernel with exact dtypes, layouts, optional branches before generation timing.
2. Verify Numba disk-cache reuse in a second process and invalidate by Numba/Python/CPU compatibility.
3. Choose one outer parallel layer. Numba-parallel IC/neutralization implies joblib tree evaluation serial or tightly bounded.
4. Pin BLAS threads to one during candidate-parallel work unless profiling proves otherwise.
5. Reuse one persistent worker pool across batches and generations.

### Priority 6: Reject earlier

1. Run deterministic cheap screening on a small date sample before full neutralization.
2. Physically compact survivor columns after fold 1.
3. Cache exact duplicate tree hashes and reusable subtree outputs within generation.
4. Run diversity/HOF correlation only for candidates passing base-fitness threshold; reuse candidate ranks.

## Delivery and Acceptance

Sequence: instrumentation; pre-ranked target/direct IC reduction; prefactored neutralization/pre-neutralized target; in-place tiled buffers; JIT warm-up/thread control; early screening.

Each stage requires the same 300,000-row fixture, cold/warm timings, peak RSS, candidates/second, numerical parity, and PIT parity. Acceptance target after priorities 1-3: at least 3x warm-generation speedup, no material fitness ordering change, no PIT behavior change, bounded peak memory below baseline.

## Repo-Local Source Evidence

Exact repo-local files read:

- `.agents/AGENTS.md`
- `.agents/agent/it-systems-auditor.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/server-management/SKILL.md`
- `.agents/skills/deployment-procedures/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`
- `src/omega/quant/evolution/genetic_engine.py`
- `scripts/genetic_alpha_evolution_v4.py`
- `scripts/run_weekly_evolution.py`
- `.ly_state/session/phase_gates.json`

Forbidden path scan result: **PASS**. Matches occurred only in authoritative repo-local SOD policy files as prohibition examples. No Antigravity scratch, OpenClaw skill, global `C:\Users\GHC\.agents`, or Codex memory path was read or used as an authoritative source. No Antigravity scratch path was read or written.

## Verdict

[APPROVED]
