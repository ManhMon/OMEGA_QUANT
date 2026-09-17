# Code Review Audit Report

- Role: `code-reviewer` (Role 21, L3 Codex)
- UTC: 
2026-07-28T03:42:34Z
- Submission: `l2_role15_vci_lock_safety_fix2_20260728`
- L2 writer: `data-engineer` (Role 15)

## Repo-Local Sources

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/l2_role15_vci_lock_safety_fix2_20260728.md`

## Evidence

- Writer/auditor separation: Role 15 != Role 21.
- Held FD primitive: `msvcrt.locking` on Windows; `fcntl.flock` on POSIX.
- Unlock only releases/closes held FD; no `lock_path.unlink()`.
- Candidate private bytes/hash/parse replacement test runs on Windows.
- Focused: 7 passed. Combined: 24 passed, 16 skipped.
- Forbidden-path scan: no authoritative target usage.

## Blocking Findings

1. **[scripts/update_market_data.py:1257]**: `os.stat(lock_path)` is only a snapshot. On POSIX, replacement after it leaves the returned lease on a detached inode and exposes an unlocked replacement pathname; a second writer can acquire that pathname concurrently.
2. **[tests/test_vci_final_safety_closure_20260728.py:67]**: Stale recovery has no actual replacement injection before/after the pathname identity check. It proves unchanged stale recovery only.

## Required Fix

- Preserve or fail closed on pathname ownership across stale claim through protected publication.
- Add real Windows/POSIX stale-claim replacement race: no second lease can own active pathname; no stat mocks.

## Verdict

[NEEDS_FIX]
