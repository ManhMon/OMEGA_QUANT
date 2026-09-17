# L2 Implementation Report

- Session: `l2_role15_vci_lock_safety_fix2_20260728`
- Role: `data-engineer` (Role 15, L2 OpenCode)
- Gate: `role21_vci_lock_safety_fix1_20260728`
- Lesson gate: `lessons_extraction_vci_lock_safety_fix2_20260728` exit 0 (dispatch evidence)
- Scope: primitive-bound publication-lock ownership, stale claim/release replacement races, private candidate-copy TOCTOU regression.
- Boundary: no refresh, network, live publish, data mutation, or phase-gate mutation.

## Repo-Local Sources Read

- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- Forbidden-path scan: no authoritative reliance on `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`.

## Implemented

- Lock lease now holds an OS primitive on the opened lock object: `fcntl.flock` on POSIX, `msvcrt.locking` on Windows.
- Stale recovery opens and claims the existing object through its held descriptor; no stale rename/unlink pathname sequence remains.
- Final unlock validates token and `os.fstat(lease.fd)` identity, then releases/closes the held descriptor; it never unlinks `lock_path`.
- Windows replacement is rejected while the lock handle is held; POSIX replacement cannot affect the held lease object.
- Added actual filesystem replacement race coverage at stale claim and final unlock, plus private candidate bytes/hash/parse replacement coverage. Tests do not mock `stat`.

## Verification

- `python -m py_compile scripts/update_market_data.py tests/test_vci_final_safety_closure_20260728.py` exit 0.
- `python -m pytest -o addopts='' tests/test_vci_final_safety_closure_20260728.py -q` exit 0: `7 passed` on Windows.
- Pytest emitted existing vnstock/deprecation/cache warnings only.
- `git diff --check`: existing unrelated worktree warnings only; no new changed-file whitespace finding attributable to this patch.

## Boundary

- No L3 audit or approval performed.
- No Codex invocation.
- No refresh, network, live publication, data, or phase-gate mutation.
