# L2 Role 9 Diagnostic Report: GP Threads Backend Exit Investigation

## Scope
- `scripts/run_weekly_evolution.py`
- `src/omega/quant/evolution/diverse_alpha_evolution.py`

## Repo-Local Files Read
- `.agents/agent/backend-engineer.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/python-patterns/SKILL.md`
- `scripts/run_weekly_evolution.py`
- `src/omega/quant/evolution/diverse_alpha_evolution.py`
- `src/omega/governance/validate_ly_state.py`

## Forbidden Path Scan Result
- No authoritative reads from forbidden skill/role roots.
- Scan result: no repo files found under `.gemini/**`, `.openclaw/**`, `.codex/**` in workspace root during this diagnostic.
- One repo document references a forbidden path as historical evidence only: `docs/L3_AUDIT_PIPELINE_CONNECTIVITY_20260526.md`.

## Commands Run
1. Large threads run:
   - `python3 scripts/run_weekly_evolution.py --generations 2 --population-size 200 --engine diverse --workers 4 --backend threads --no-alt-features`
2. Small threads run:
   - `python3 scripts/run_weekly_evolution.py --generations 1 --population-size 20 --engine diverse --workers 2 --backend threads --no-alt-features`
3. OOM evidence checks:
   - `dmesg 2>/dev/null | grep -i 'killed process' | tail -5`
   - `/var/log/kern.log` tail if readable
4. Isolating probes:
   - `.ly_state/session/pre_thread_probe_20260716.py`
   - `.ly_state/session/pre_thread_probe_no_alt_20260716.py`

## Runtime Evidence

### Large run captured output
File: `.ly_state/session/threads_large_all_output.txt`

Observed last lines:
- `Prepared data: 1734598 rows after lag/dropna`
- `Alternative features available: 0 / 35`

Not observed:
- `Sliding walk-forward split ...`
- `Diverse evaluation parallelism: backend=threading requested_n_jobs=4 seed=42`

### Small run captured output
File: `.ly_state/session/threads_small_all_output.txt`

Observed last lines:
- `Prepared data: 1734598 rows after lag/dropna`
- `Alternative features available: 0 / 35`

Not observed:
- `Sliding walk-forward split ...`
- `Diverse evaluation parallelism: backend=threading requested_n_jobs=2 seed=42`

### OOM checks
File: `.ly_state/session/dmesg_tail_20260716.txt`

Result:
- No `Killed process` lines found.
- `/var/log/kern.log` was not readable / not present from this session, so no corroborating kernel OOM record there.

## Isolation Result

### Probe without `--no-alt-features`
Command path: `.ly_state/session/pre_thread_probe_20260716.py`

Observed:
- `prepare_features()` completed.
- `walk_forward_split()` completed.
- Output included:
  - `PROBE:prepared rows=1222680`
  - `Sliding walk-forward split [Regime: all]: train=647105 rows ...`

### Probe matching `--no-alt-features` monkey-patch
Command path: `.ly_state/session/pre_thread_probe_no_alt_20260716.py`

Observed:
- `prepare_features()` completed.
- `walk_forward_split()` completed.
- Output included:
  - `PROBE_NO_ALT:prepared rows=1734598`
  - `Sliding walk-forward split [Regime: all]: train=986302 rows ...`

This proves the pre-evolution data path is viable in isolation, including the `--no-alt-features` branch.

## Code Inspection: Threading Dispatch / Shared State

### Dispatch location
In `src/omega/quant/evolution/diverse_alpha_evolution.py`:
- `run()` logs `Diverse evaluation parallelism...` at lines 1087-1092.
- Population evaluation happens in `_evaluate_population()` at lines 873-966.
- Joblib pool creation happens in `_ensure_parallel_pool()` at lines 813-834.
- Backend normalization maps `threads` to `threading` at line 684.

### Synchronization / shared-state used
- Explicit threading primitive found: `_MemoryHeadroomGuard` uses `threading.Event` and a daemon `threading.Thread` at lines 412-449.
- In this execution path, `memory_guard_enabled=False` is set in `scripts/run_weekly_evolution.py` lines 981-996, so that guard thread is disabled for the diverse engine run.
- No `Lock`, `RLock`, `Semaphore`, or `Condition` found in `diverse_alpha_evolution.py`.
- Thread backend path does not use memmap worker globals. Those are only used for process backends (`loky`, `multiprocessing`) via `_open_shared_worker_context()` and `_init_worker_globals()`.
- Thread backend passes in-process objects directly to `_evaluate_genome_job()` from `_evaluate_population()` lines 930-946.
- `_candidate_from_genome_standard()` catches all exceptions and returns `None` at lines 593-676, which can hide worker exceptions during evaluation but would only matter after the `Diverse evaluation parallelism...` log appears.

## Conclusion

### Hypothesis A: WSL OOM killer silently kills the process
Status: **not supported by evidence**.

Evidence:
- No `Killed process` entries in captured `dmesg` tail.
- Failure reproduced for both large and small runs before any diverse-engine logging.
- Isolated no-alt probe successfully completed `prepare_features()` and `walk_forward_split()` under WSL.

Limit:
- Absence of `dmesg` evidence is not a mathematical proof, but current evidence does not support OOM as the primary cause.

### Hypothesis B: thread-pool deadlock in joblib ThreadsBackend / BLAS / eval lock
Status: **ruled out for this reported failure point**.

Evidence:
- The failing captured runs never reached the log line `Diverse evaluation parallelism...` in `DiverseAlphaEvolution.run()`.
- Therefore the process did not enter the thread-pool evaluation section in `diverse_alpha_evolution.py`.
- No lock-based synchronization was found in the target file beyond the optional memory guard thread, which is disabled in the diverse-engine config from `run_weekly_evolution.py`.

## Most Likely Interpretation
- The observed failing runs are not stalling at the diverse threaded evaluation dispatch. They terminate earlier in `scripts/run_weekly_evolution.py`, after `prepare_features()` logging and before or during the transition into `walk_forward_split()` / `run_evolution()`.
- Because the direct probe scripts completed that same path, the most plausible explanation is an execution-environment artifact in the exact wrapper/timeout invocation rather than a threads backend deadlock.
- Secondary contributing factor: exception visibility is poor in the diverse engine because `_candidate_from_genome_standard()` swallows all exceptions, but that is downstream of the currently observed failure point.

## Artifacts Written
- `.ly_state/session/threads_large_all_output.txt`
- `.ly_state/session/threads_small_all_output.txt`
- `.ly_state/session/threads_small_diag_stderr.log`
- `.ly_state/session/threads_diag_stderr.log`
- `.ly_state/session/dmesg_tail_20260716.txt`
- `.ly_state/session/pre_thread_probe_20260716.py`
- `.ly_state/session/pre_thread_probe_no_alt_20260716.py`
- `.ly_state/session/pre_thread_probe_no_alt_output.txt`
- `.ly_state/session/wsl_threads_diag_20260716.sh`
- `.ly_state/session/wsl_exact_small_threads_20260716.sh`

## Verdict
- **Neither requested hypothesis matches the captured failure.**
- **Current evidence favors a pre-thread failure / wrapper-effect, not OOM, not thread-pool deadlock.**
