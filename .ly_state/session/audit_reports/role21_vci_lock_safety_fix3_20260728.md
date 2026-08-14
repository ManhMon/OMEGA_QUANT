# Code Review Audit Report

- role: `21 code-reviewer` (L3 Codex)
- submission: `l2_role15_vci_lock_safety_fix3_20260728`
- L2 writer: `15 data-engineer` (distinct from L3 role 21)
- date: `2026-07-28`
- audit scope: `scripts/update_market_data.py`, `tests/test_vci_final_safety_closure_20260728.py`, `tests/test_vci_production_safety_20260727.py`

## Repo-Local Authority Evidence

Read:

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

Forbidden-path scan: no authoritative reliance found in the L2 report. References inside repo-local `audit-cycle` and `omega-sod` skill files are policy documentation, not authority loading.

## Evidence

- Expired/existing lock: `_acquire_publication_lock()` converts every `FileExistsError` to `RuntimeError("publication lock held; operator recovery required")` at `scripts/update_market_data.py:1216`.
- Replacement race: `test_stale_path_replacement_race_fails_closed_and_preserves_active_lock` uses real `os.replace`; focused suite passes.
- Active replacement preservation: `_release_publication_lock()` intentionally never unlinks the pathname at `scripts/update_market_data.py:1239`.
- Focused verification: `python -m pytest tests/test_vci_final_safety_closure_20260728.py -q` — `7 passed`.
- Combined verification: `python -m pytest tests/test_vci_final_safety_closure_20260728.py tests/test_vci_production_safety_20260727.py -q` — `9 passed, 2 skipped`.
- Diff whitespace: `git diff --check -- scripts/update_market_data.py tests/test_vci_final_safety_closure_20260728.py tests/test_vci_production_safety_20260727.py` — clean.

## Blocking Issue

1. **[scripts/update_market_data.py:1239]**: Normal owner release never removes its own lock pathname. `O_CREAT | O_EXCL` therefore rejects every later publication even after the prior lease closes. Direct runtime probe: acquire, release, then reacquire prints `path_exists_after_release=True` and `publication lock held; operator recovery required`. This fails the required fresh-lock lifecycle and makes normal sequential publishing operator-blocked.

The current test codifies the bad lifecycle with `assert lock.exists()` in `tests/test_vci_final_safety_closure_20260728.py:65`; it lacks a successful acquire-release-acquire regression case.

## Verdict

[NEEDS_FIX]

Required L2 remediation: preserve the replacement-race guarantee while restoring safe release of an unchanged owner lock, then add a regression test proving acquire-release-acquire succeeds. Re-run focused plus combined suite.