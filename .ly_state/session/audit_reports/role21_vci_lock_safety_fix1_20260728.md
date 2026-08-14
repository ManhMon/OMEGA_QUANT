# Code Review Audit Report

- Role: `code-reviewer` (Role 21, L3 Codex)
- UTC: `2026-07-28T03:18:30Z`
- Submission: `l2_role15_vci_lock_safety_fix1_20260728`
- Gate: `task-12788`
- L2 writer: `data-engineer` (Role 15)

## Sources

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/l2_role15_vci_lock_safety_fix1_20260728.md`

## Checks

- Writer/auditor separation: Role 15 != Role 21.
- Scope: no source/data/gate edits made by L3.
- UTC run ID: implemented via `datetime.now(timezone.utc)`.
- Receipt session guard: rejects missing/blank `expected_date` before `pd.Timestamp` conversion.
- Exception ordering: `official_watermark.py` canonicalizes immutable JSON order before hash and persistence.
- Windows quarantine: quarantine bytes are written and fsynced; no unsupported Windows directory-durability claim.
- Focused: `python -m pytest tests/test_vci_final_safety_closure_20260728.py -q` -> `8 passed`.
- Combined: `python -m pytest tests/test_official_watermark.py tests/test_vci_production_safety_20260727.py tests/test_vci_final_safety_closure_20260728.py tests/test_market_release_gates.py -rA` -> `25 passed, 16 skipped`.
- Forbidden-path scan: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `.codex\memories` absent. `C:\Users\GHC\.agents` present but not read or relied upon.

## Blocking Findings

1. `scripts/update_market_data.py:1223`: stale recovery evaluates stale content, then later calls `os.rename(lock_path, claim_path)` without binding the rename to the inspected file identity. A path replacement between those operations can move a newly active lock into the stale claim. The contention test only inserts a competing lock after the rename; it does not cover this interleaving.
2. `scripts/update_market_data.py:1245`: unlock re-stats the path then calls `lock_path.unlink()` as a separate pathname operation. The identity check is not an atomic compare-and-delete. A replacement after the final `os.stat` can be deleted. `tests/test_vci_final_safety_closure_20260728.py:100` fabricates a different `stat` result; it never replaces the pathname after the final identity check.
3. `tests/test_vci_final_safety_closure_20260728.py:119`: the private-copy test only validates an unchanged candidate. It is not Windows-specific and injects no mutation/replacement between candidate read, hash validation, and parquet parse. Requirement `Windows private-copy TOCTOU executes` remains unproven.

## Verdict

[NEEDS_FIX]

Use a lock primitive whose claim/release operation is bound to the held object across Windows and POSIX, then add deterministic actual pathname-replacement races for stale claim, final unlock, and Windows candidate replacement.