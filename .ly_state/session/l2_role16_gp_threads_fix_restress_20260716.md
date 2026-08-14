# L2 Report: GP Threads Fix Restress

Date: 2026-07-16
Requested role label: `16 data-engineer`
Repo-local role frontmatter parsed: `name=data-engineer`, `role_id=15`, `tier=2`, `platform=OpenCode`
Scope: `scripts/run_weekly_evolution.py`, `src/omega/quant/evolution/diverse_alpha_evolution.py`
Action: read-only verification, no source edits

## Repo-Local Files Read

- Role: `.agents/agent/data-engineer.md`
- Skills:
  - `.agents/skills/python-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
- Task-relevant repo files:
  - `scratch/stress_test.sh`
  - `scripts/run_weekly_evolution.py`
  - `src/omega/quant/evolution/diverse_alpha_evolution.py`

## Forbidden Path Scan Result

No authoritative reliance on forbidden paths.

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative; not used as source.
- `.openclaw\skills`: non-authoritative; not used as source.
- `C:\Users\GHC\.agents`: non-authoritative; not used as source.
- `.codex\memories`: non-authoritative; not used as source.

Note: broad repo grep finds these strings in SoD contract and prior audit/report files only. None were used as authoritative role/skill sources for this task.

## Commands Run

WSL working pattern adapted from `scratch/stress_test.sh`:

```bash
cd /mnt/c/Users/GHC/repos/OMEGA_QUANT
export PYTHONPATH=src
export PYTHONUNBUFFERED=1
```

Threads backend:

```bash
/usr/bin/time -v -o .ly_state/session/role16_threads_restress_time_20260716.log \
  python3 scripts/run_weekly_evolution.py \
  --generations 2 \
  --population-size 200 \
  --engine diverse \
  --workers 4 \
  --backend threads \
  --no-alt-features \
  > .ly_state/session/role16_threads_restress_stdout_20260716.log \
  2> .ly_state/session/role16_threads_restress_stderr_20260716.log
```

Loky backend:

```bash
/usr/bin/time -v -o .ly_state/session/role16_loky_restress_time_20260716.log \
  python3 scripts/run_weekly_evolution.py \
  --generations 2 \
  --population-size 200 \
  --engine diverse \
  --workers 4 \
  --backend loky \
  --no-alt-features \
  > .ly_state/session/role16_loky_restress_stdout_20260716.log \
  2> .ly_state/session/role16_loky_restress_stderr_20260716.log
```

## Parameter Verification

- `--population-size 200` with `engine=diverse` maps to `4 islands x 50 pop` inside `scripts/run_weekly_evolution.py`.
- `--generations 2` confirmed.
- `--workers 4` confirmed.
- `--backend threads|loky` confirmed.
- `--no-alt-features` confirmed.
- Input size loaded: `1,776,743` rows.
- Prepared rows after lag/dropna: `1,734,598`.

## Results

### 1. Threads

- Exit code: `1`
- PeakRSS: unavailable from `/usr/bin/time` output because `role16_threads_restress_time_20260716.log` remained empty on failure.
- Completion: failed before completion.
- `InsufficientMemoryError`: not observed.
- Last log lines:
  - `INFO:weekly_evolution:Using n_jobs=4`
  - `INFO:omega.quant.evolution.diverse_alpha_evolution:=== DIVERSE EVOLUTION: 4 islands x 50 pop x 2 gen ===`
  - `INFO:omega.quant.evolution.diverse_alpha_evolution:Diverse evaluation parallelism: backend=threading requested_n_jobs=4 seed=42`

Assessment: the prior `InsufficientMemoryError` did not recur in this restress run, but the threads backend still does not complete successfully under the requested large-run settings.

### 2. Loky

- Exit code: `0`
- PeakRSS: `8,293,768 kbytes` = `8099.38 MiB` = `8492.82 MB`
- Completion: PASS
- Completion markers present:
  - `=== DIVERSE EVOLUTION COMPLETE: 4 alphas, 912.0s ===`
  - `=== WEEKLY GP ALPHA EVOLUTION COMPLETE ===`

## Baseline Comparison

Prior baseline provided:

- loky: PASS, peak `9030 MB`
- threads: FAIL with `InsufficientMemoryError`

Current restress:

- loky: PASS, peak `8492.82 MB` (`8099.38 MiB`), about `537.18 MB` lower than prior baseline.
- threads: FAIL, but not with observed `InsufficientMemoryError`; failure occurs after threaded diverse evaluation starts.

## Conclusion

Threads backend does **not** complete successfully yet under:

- pop=`200`
- islands=`4`
- generations=`2`
- rows about `1.7M`
- workers=`4`
- backend=`threads`
- `--no-alt-features`

Specific question answer: threads backend now gets past the prior `InsufficientMemoryError`, but it still does not complete the stress test successfully.

## Artifacts

- `.ly_state/session/role16_threads_restress_stdout_20260716.log`
- `.ly_state/session/role16_threads_restress_stderr_20260716.log`
- `.ly_state/session/role16_threads_restress_time_20260716.log`
- `.ly_state/session/role16_loky_restress_stdout_20260716.log`
- `.ly_state/session/role16_loky_restress_stderr_20260716.log`
- `.ly_state/session/role16_loky_restress_time_20260716.log`
