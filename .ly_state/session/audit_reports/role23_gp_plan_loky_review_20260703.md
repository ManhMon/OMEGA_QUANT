# Performance Plan Audit Report
**Role**: Performance Tester (Role 23)  
**Date**: 2026-07-03  
**Gate**: GP_PERFORMANCE_PLAN_REVIEW_20260703  
**Submission**: Complete GP optimization roadmap, Gates 1-3  
**Verdict**: [NEEDS_FIX]

## Repo-Local Source Evidence
- Role spec read: `.agents/agent/performance-tester.md`
- Parsed frontmatter: `name=performance-tester`, `role_id=23`, `tier=3`, `platform=Codex`, `skills=[performance-profiling, webapp-testing, audit-cycle, systematic-debugging]`
- Repo-local skills read:
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/webapp-testing/SKILL.md`
  - `.agents/skills/audit-cycle/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
- Repo files inspected:
  - `src/omega/quant/evolution/genetic_engine.py`
  - `scripts/genetic_alpha_evolution_v3.py`
  - `.ly_state/session/audit_reports/role23_gp_performance_20260703.md`
- Submitted plan documents read by filename: `gp_performance_optimization_plan.md`, `gp_performance_optimization_loky_addendum.md`, `gp_performance_optimization_gate3_addendum.md`
- Forbidden path scan result: no non-repo role or skill source used as authoritative input. Submitted non-repo plan files were reviewed only as user-provided artifacts.

## Findings
1. **Gate 2 Fix A is not mathematically exact with pairwise NaNs as written.**  
   The plan says to rank alpha once and compare to precomputed baseline ranks, with a NaN-containing equivalence test. That does not generally match `spearmanr()` after pairwise `dropna()`, because ranks must be computed on the same pairwise-valid subset. Current V3 data path drops baseline NaNs and `evaluate()` converts alpha NaNs to zero, so the optimization can be exact under a finite-array precondition, but the plan must state that precondition or rank alpha per baseline valid mask. Required correction: replace the NaN-equivalence claim with one of:
   - assert/document finite `ortho_baseline_set` and post-cleaned finite alpha, then test ties and finite parity; or
   - support baseline/alpha NaNs by ranking alpha on each baseline pairwise-valid mask.

2. **Gate 1 Extra-2 changes observation-threshold semantics for `inf` targets.**  
   Current code uses `pd.DataFrame(...).dropna()`, which drops NaN but keeps `inf`; the plan says `valid_mask = np.isfinite(target)`, which drops `inf`. `_compute_combined_ic()` already filters non-finite values for IC, but the `min_observations` guard would change. Required correction: use `pd.notna(target)` or explicitly document the behavior change and adjust tests. For rollback-equivalent behavior, use `pd.notna(target)`.

3. **Loky default rationale is directionally plausible but not implementation-ready as a default switch.**  
   Local probe confirms `parallel_backend("loky")` overrides `Parallel(..., prefer="threads")`, so changing `scripts/genetic_alpha_evolution_v3.py` can route engine evaluation through processes. But "numpy releases GIL -> use loky" is not sufficient: GIL-releasing numpy also benefits threads, while loky pays process serialization and duplicated memory costs for feature dicts, HoF caches, fold caches, and neutralization caches. Required correction: make loky promotion benchmark-gated, not unconditional. Default should change to loky only after the plan's own criteria pass: `>=10%` faster than threads, three consecutive stable runs, acceptable `[WinError 5]` rate, and memory within budget.

4. **Gate 3 Option A is feasible, but current implementation steps are underspecified.**  
   `GPIndividual.evaluate()` currently executes tree, winsorizes, z-scores, neutralizes, computes IC, then penalties per individual. "Stack alphas in `evolve()` before passing to neutralization" requires splitting evaluation into at least execute/preprocess and score phases, or adding a batch neutralization path that preserves current per-individual preprocessing and time-fold neutralization semantics. Required correction: add the exact refactor boundary and data flow:
   - execute + clean + winsorize + z-score all population alphas;
   - batch neutralize per fold/date using shared valid rows;
   - pass neutralized alphas into unchanged scoring/penalty logic;
   - preserve sequential and parallel behavior under feature flags.

5. **Gate 3 Option B risks are partly documented but missing current-code equivalence constraints.**  
   Current neutralization skips dates when `rank < design_valid.shape[1]`; a pseudoinverse or projection matrix would still produce residuals unless the same rank policy is applied. Full `P = I - X @ pinv(X)` per date can also be memory-heavy. Required correction: document rank-deficient-date behavior, prefer cached QR/SVD factors or a residual-maker operator over full dense `P`, and keep projection opt-in only.

## Check Results
- Gate 1 Extra-1 HoF cache: feasible and thread-safe if HoF alphas are built before `Parallel()` and injected read-only through `gen_features`.
- Gate 1 Extra-2 numpy: feasible after `pd.notna` vs `isfinite` correction.
- Gate 1 loky backend: keep as measured candidate; do not make default until benchmark gate passes.
- Gate 2 Fix C fold cache: feasible and PIT-safe when keyed by current `__date__` identity/length/fold config and rebuilt per feature slice.
- Gate 2 Fix A ortho ranks: feasible only under finite-array precondition or per-baseline valid-mask ranking.
- Gate 3 Option A batch LSTSQ: feasible, recommended, but needs concrete refactor plan before L2 implementation.
- Gate 3 Option B projection: high risk; acceptable only as later opt-in after Option A and profiling.
- Complete roadmap speedup: `4-6x` is a reasonable target if Gate 3A proves neutralization dominance. `15x` is an optimistic upper bound, not an implementation promise.
- Test coverage: good outline, but missing required parity tests for pairwise NaN ranking, `inf` target threshold behavior, loky vs threads result stability, and Gate 3 rank-deficient neutralization.

## Required Corrections
1. Update Fix A to remove the false global-rank NaN equivalence claim or implement per-baseline valid-mask ranking.
2. Update Extra-2 to preserve `dropna()` threshold semantics with `pd.notna(target)` unless an intentional behavior change is approved.
3. Change loky from unconditional default change to benchmark-gated default promotion.
4. Expand Gate 3 Option A with the exact batch-evaluation refactor boundary and preservation of per-individual preprocessing/time-fold semantics.
5. Add Gate 3 Option B rank-deficiency and memory constraints.
6. Add tests for all corrected edge cases above.

## Inline Fix Authority
These are plan-level corrections, not production code changes. They can be made inline in the plan documents by L1/L2 without a new design cycle if the wording and tests above are adopted. If Gate 3 Option A changes the evaluation architecture beyond the described split, require L1 revision before implementation.

## Verdict
[NEEDS_FIX]

Gates 1 and 2 are close, but not implementation-ready until the exactness and loky-default issues are corrected. Gate 3 is directionally sound but needs a concrete batch-neutralization refactor plan before approval.
