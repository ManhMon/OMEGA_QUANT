# GP Comprehensive Bottleneck Roadmap

- Date: `2026-07-24`
- Status: `PLANNING_APPROVED_FOR_EXECUTION`
- Source: mirrored from approved artifact plan, corrected per L3 verdict
- Purpose: repo-local authoritative roadmap for comprehensive evolution-stack bottleneck remediation

## L3 Decisions Locked

- Roadmap organized by **bottleneck class**
- Implementation tickets split by **module**
- **Gate isolation is absolute**
- `OUT_OF_SCOPE` allowed only with pre-patch baseline evidence
- Keep phases **A / B / C**
- Module priority:
  1. `scripts/run_weekly_evolution.py`
  2. `src/omega/quant/evolution/diverse_alpha_evolution.py`
  3. `src/omega/quant/evolution/genetic_alpha.py`
- Shared kernel is **not** a Phase A task

## Benchmark Contract

Every performance gate must use:
- same dataset
- same seed
- same config
- same machine
- `1` warm-up + `3` measured runs
- report:
  - median wall-clock
  - max RSS
  - candidate throughput
  - hotspot ranking

## Acceptance Gates

### Phase A
- hot-path median improvement `>=20%`
- output parity `equal_nan=True`
- tolerance declared in advance

### Phase B
- peak RSS reduction `>=25%`
- runtime regression `<=5%`
- `3` weekly smoke runs with no OOM

### Phase C
- weekly wall-clock reduction `>=30%`
- candidate throughput increase `>=25%`
- checkpoint recovery parity preserved

## PIT / Behavior Invariants

- split boundaries unchanged
- embargo unchanged
- masks unchanged
- cache only metadata independent of labels
- never cache signal/fitness across folds
- candidate ordering / selected set / HoF / promotion decisions must preserve parity under fixed seed

## SoD Rules For Every Gate

- one gate = one bottleneck
- one gate = one L2 report
- one gate = one L3 audit
- shared helper changes require dedicated gate
- explicit changed-files allowlist required before dispatch
- repo-local evidence must use repo-relative paths
- forbidden paths must be labeled `(non-authoritative scan)`

## Ordered Gate Sequence

1. **Gate 1** — weekly baseline benchmark + profiling
2. **Gate 2** — remaining Spearman fallback in `src/omega/quant/evolution/genetic_engine.py`
3. **Gate 3** — `_fold_values` lifecycle in `src/omega/quant/evolution/hybrid_alpha_miner.py`
4. **Gate 4** — worker oversubscription / data load / sequencing in `scripts/run_weekly_evolution.py`
5. **Gate 5** — island parallelism in `src/omega/quant/evolution/diverse_alpha_evolution.py`
6. **Gate 6+** — shared kernel / pooled execution / shared feature preparation if benchmark-justified

## Gate 1 Scope

Files in scope:
- `scripts/measure_perf_baseline.py`
- `scripts/profile_performance.py`
- `scripts/profile_bottlenecks.py`
- `scripts/run_weekly_evolution.py` (observation/profiling only unless a later gate explicitly broadens scope)

Deliverables:
- baseline report
- hotspot ranking
- max RSS / wall-clock / throughput table
- changed-files allowlist proposal for Gate 2+

Non-goals:
- no engine refactor
- no shared kernel extraction
- no unrelated behavior cleanup
