# Performance Test Audit Report
**Role**: Performance Tester (Role 23)
**Date**: 2026-07-03
**Gate**: GP_PERFORMANCE_AUDIT_20260703
**Submission**: Claude Code advisory `claude_code_advisory_20260703`
**Scope**: `scripts/genetic_alpha_evolution_v3.py`, `src/omega/quant/evolution/genetic_engine.py`

## Repo-Local Source Evidence
- Role spec read: `.agents/agent/performance-tester.md`
- Parsed frontmatter: `name=performance-tester`, `role_id=23`, `tier=3`, `platform=Codex`, `skills=[performance-profiling, webapp-testing, audit-cycle, systematic-debugging]`
- Repo-local skills read:
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/webapp-testing/SKILL.md`
  - `.agents/skills/audit-cycle/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
- Protocol file read: `.agents/AGENTS.md`
- Scope files read:
  - `scripts/genetic_alpha_evolution_v3.py`
  - `src/omega/quant/evolution/genetic_engine.py`
- Supporting repo-local evidence read:
  - `.ly_state/session/gp_improvement_plan_20260703.md`
- Forbidden path scan result: no Antigravity scratch/OpenClaw/global-agent/Codex-memory paths were read or used as authoritative sources. Repo-local scan of the read protocol/role/skill/scope files found only non-authoritative forbidden-path mentions in `.agents/AGENTS.md` and `.agents/skills/audit-cycle/SKILL.md`.

## Code Inspection Findings
1. **Claude bottleneck #1 confirmed, but understated cache bug**: diversity and orthogonalization penalties perform repeated pandas `DataFrame(...).dropna()` plus `spearmanr()` work per individual. Evidence: `genetic_engine.py:543-604`. With `hall_of_fame_size=10` and five orthogonalization baselines from `genetic_alpha_evolution_v3.py:193,211,221`, this can reach about 15 correlations per evaluated individual. Additional issue: the intended HoF alpha cache is ineffective because `hall_of_fame` is a plain `list`; assigning `hall_of_fame._alpha_cache` raises and is swallowed (`genetic_engine.py:548-560`). Result: HoF alphas are recomputed repeatedly.
2. **Claude bottleneck #2 partly confirmed, but fix claim is unsafe as stated**: V3 enables full-sample `use_time_fold_ir=True` (`genetic_alpha_evolution_v3.py:215-217`). Current engine intentionally disables random 100k row subsampling when time-fold IR is active (`genetic_engine.py:1135-1147`) to preserve chronological fold structure. Any proposed row-level subsampling inside fold IR is not zero-IC-impact; it changes fitness. Only deterministic, date/fold-stratified approximation is acceptable as an opt-in speed mode with measured error bounds.
3. **Claude bottleneck #3 confirmed**: `_compute_time_fold_ir()` recomputes valid dates, split dates, `np.isin` fold masks, fold feature slices, and validity masks for every individual (`genetic_engine.py:135-167`). Precomputing fold indices/masks once per `features['__date__']` identity is performance-safe.
4. **Additional missed bottleneck**: `evaluate()` builds `combined = pd.DataFrame(...).dropna()` solely for the observation count after `alpha_series` has already been `nan_to_num`-cleaned (`genetic_engine.py:500-508`). A numpy finite target mask/count is enough.
5. **Additional missed bottleneck**: `_compute_time_fold_ir()` constructs `fold_features` by slicing every feature array per fold per individual (`genetic_engine.py:151-155`), though neutralization needs only date, market-cap, and sector metadata.
6. **No-results lesson addressed**: result export is guarded by `if results_for_save:` (`genetic_alpha_evolution_v3.py:288-302`), so empty HoF no longer crashes on `exported_rows[0]`.

## Fix A-C Assessment
- **Fix A: replace pandas dropna/correlation loops with numpy masks/precomputed ranks**: approved if it preserves scipy Spearman tie semantics or includes a numeric equivalence test. PIT-safe because it only changes in-sample fitness computation mechanics; no future data access added.
- **Fix B: subsample time-fold IR full 200K evaluation**: needs correction. Row-random subsampling conflicts with chronological fold IR and is not zero IC impact. Acceptable version: precompute chronological folds on full dates, then use deterministic per-fold/date-stratified indices only in explicit fast mode; final HoF scoring must use full data.
- **Fix C: precompute fold masks/indices**: approved. Cache by `id(date_arr)`/length/fold config and rebuild when feature slice changes. PIT-safe; no scoring semantics change.

## Profiling Validation
- Recommended approach: benchmark one generation with `workers=1` first, then `threads`; profile `GPIndividual.evaluate`, `_compute_time_fold_ir`, diversity/ortho penalty sections, and `_execute_tree`.
- Use `cProfile`/`pstats` for call-level ranking plus lightweight `perf_counter` section timers already present in fold/neutralization helpers. Avoid profiling five full rounds before isolating one-generation hotspots.
- Validate each optimization with before/after wall-clock per generation and IC equivalence or bounded approximation error.

## Backend Recommendation
- Keep default backend as threads. Current CLI defaults `--backend threads` (`genetic_alpha_evolution_v3.py:66-70`) and maps it to joblib `threading` (`genetic_alpha_evolution_v3.py:231-234`); engine also uses `Parallel(..., prefer='threads')` (`genetic_engine.py:1170-1177`).
- Avoid `loky`/`multiprocessing` as defaults on this Windows repo due known worker permission failures and higher serialization cost for large numpy arrays. Processes can remain opt-in for machines where they are proven faster and stable.

## PIT Safety
- Current feature engineering shifts terminal features, log market-cap proxy, and sector proxy by ticker before training (`genetic_alpha_evolution_v3.py:83-96`): PIT-safe.
- Orthogonalization baselines use shifted train features only (`genetic_alpha_evolution_v3.py:183-193`): PIT-safe.
- Precomputed diversity/ortho/fold caches are PIT-safe only if keyed to the current feature slice and never reused across train/test or changed sample masks.
- Time-fold subsampling is PIT-safe only when deterministic and fold/date-stratified; row-random subsampling is a semantics/regression risk even if it does not introduce look-ahead.

## Verdict
[NEEDS_FIX]

Claude's A and C recommendations are safe to implement with equivalence tests. Claude's B recommendation must be corrected before implementation because the stated "zero IC impact" claim is false for subsampled time-fold IR.
