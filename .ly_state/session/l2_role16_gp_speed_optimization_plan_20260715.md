# L2 Report - role16 - gp_speed_optimization_plan - 20260715

## Summary

- Updated `.ly_state/session/gp_speed_optimization_plan.md` từ V6 sang V7.
- Reframed plan để đóng đủ 6 gaps của L3 trong `gp_speed_optimization_plan_review`, không còn chỉ 4 blocker cũ.
- Giữ nguyên scope file; không đổi production code.

## Files Changed

- `.ly_state/session/gp_speed_optimization_plan.md`

## Six-Gap Coverage

1. Mask safety
   - Added exact `valid_row` predicate: row chỉ hợp lệ khi mọi input trực tiếp vào correlation đều hữu hạn, tối thiểu `alpha` và `target` phải cùng finite.
   - Added exact joint finite-mask rule: luôn dùng logical `AND`, không union, không mask độc lập từng vế.
   - Added exact minimum-observation rule: `valid_count <= 5` trả `NaN`.
   - Added exact empty/all-invalid rule: `valid_count == 0` hoặc mọi row invalid trả `NaN`.
   - Added edge fixtures và named tests cho all-invalid, exactly-five-valid, mixed mask alignment.

2. Correlation degeneracy
   - Added exact degeneracy thresholds: `alpha_variance <= 1e-12`, `target_variance <= 1e-12`, hoặc `denom <= 1e-12` trả `NaN`.
   - Added fail-closed non-finite contract: accumulator/intermediate non-finite trả `NaN`, không clip về 0.
   - Added named regression tests cho constant alpha, constant target, low denominator, non-finite accumulator, NaN propagation qua batch IR.

3. Cholesky contract
   - Retained V6 contract: Cholesky-first, invalid-diagonal precheck, `LinAlgError` fallback sang `np.linalg.solve`.
   - Added explicit invalid-diagonal regression name alongside fast-path and fallback parity tests.

4. Float32 precision
   - Added per-region dtype contract:
     - `float64` cho `design_matrix`, Gram/ridge matrices, Cholesky, `np.linalg.solve`, rank/correlation accumulators, daily IC outputs, neutralized outputs.
     - `float32` chỉ cho storage/stack buffers/cache payloads không làm solver workspace hay accumulator.
   - Added adversarial precision bounds: IC drift `<= 1e-6`, neutralization drift `<= 1e-8`.
   - Added named float32-vs-float64 regression tests.

5. Thread safety
   - Retained V6 cache synchronization contract: `threading.Lock` cho atomic check/validate/set trên `_DATE_GROUPS_CACHE`, `_GLOBAL_FOLD_FEATURES_CACHE`, target neutralization shared cache, và `_ensure_neutralization_jit_context` mutation path.
   - Retained stress-test requirements: timeout completion, deterministic output, no exception/deadlock/corruption.

6. Cache identity
   - Retained V6 cache identity contract: digest primary key + `dtype`/`shape` gate + `np.array_equal(..., equal_nan=True)` payload verification.
   - Retained forced-collision rebuild and clone-hit requirements for date-group, fold-feature, target-neutralization caches.

## Acceptance Delta Versus L3 Audit

- Gap 1 now has exact mask predicate, exact count threshold, empty/all-invalid semantics, fixtures, expected outputs.
- Gap 2 now has exact degeneracy thresholds, non-finite handling, expected `NaN` result, named regressions.
- Gap 3 remained covered from V6; V7 only tightened explicit regression naming.
- Gap 4 now has explicit per-region dtype contract and numeric bounds.
- Gap 5 remained covered from V6.
- Gap 6 remained covered from V6.

## Repo-Local Files Read

- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

## Forbidden Path Scan Result

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative only; not read as role/skill source.
- `.openclaw\skills`: non-authoritative only; not read as role/skill source.
- `C:\Users\GHC\.agents`: non-authoritative only; not read as role/skill source.
- `.codex\memories`: non-authoritative only; not read as role/skill source.

## Verification

- Plan/document edit only. No runtime tests executed.
- No production code changed.
- Scope respected: only `.ly_state/session/gp_speed_optimization_plan.md` plus this L2 report updated.

## Handoff Notes For L3

- Review should score all 6 audit gaps, not the older 4-blocker framing.
- New material in V7 is concentrated in mask-safety, correlation-degeneracy, and float32-precision sections.
