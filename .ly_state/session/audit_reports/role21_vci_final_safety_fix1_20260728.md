# Code Review Audit Report

**Role**: Code Reviewer (Role 21, L3 Codex)
**Date**: 2026-07-28
**Submission**: `l2_role15_vci_final_safety_20260728` and `l2_role15_vci_final_safety_fix1_20260728`
**Tier 2 Engineer**: `data-engineer` (Role 15, OpenCode)
**Verdict**: [NEEDS_FIX]

## Scope And SoD

- Writer/auditor separation: PASS (`15 != 21`).
- L3 source/data/gate edits: none. This report is the only L3 write.
- Required plan `vci_final_safety_closure_plan.md`: NOT PRESENT at `REPO_ROOT`; every stated plan contract cannot receive artifact-backed verification.

## Repo-Local Skill Evidence

- Role read: `.agents/agent/code-reviewer.md`.
- Skills read: `.agents/skills/code-review-checklist/SKILL.md`, `.agents/skills/clean-code/SKILL.md`, `.agents/skills/testing-patterns/SKILL.md`, `.agents/skills/audit-cycle/SKILL.md`, `.agents/skills/omega-sod/SKILL.md`.
- L2 declared role/skills: present under `.agents/agent/data-engineer.md` and `.agents/skills/*/SKILL.md`.
- Forbidden-path scan: no authoritative reliance. `C:\Users\GHC\.agents` exists but was not read; other listed forbidden paths absent from repo root. `sod_report_evidence.py` passed for both L2 reports.

## Contract Review

- FAIL: canonical exception hash is not recomputed before semantic entry checks. `src/omega/data/official_watermark.py:204` validates each entry before `exceptions_hash` is calculated at `src/omega/data/official_watermark.py:206`. This contradicts the required canonical-hash ordering.
- FAIL: stale owner-token lock recovery is not atomic. `scripts/update_market_data.py:1190` unlinks the stale lock, then recursively reacquires at `scripts/update_market_data.py:1193`; another writer can acquire during that gap. Non-owner unlock rejection itself is present at `scripts/update_market_data.py:1207`.
- PASS (static): timestamp parser rejects naive values and normalizes UTC at `src/omega/data/official_watermark.py:58`; receipt retrieval/cutoff ordering uses it at `src/omega/data/official_watermark.py:199`.
- PASS (static): Windows directory durability fails closed, without a false fsync claim, at `scripts/update_market_data.py:176` and `src/omega/data/official_watermark.py:135`.
- PASS (static): reader consumes verified pointer/candidate bytes through private `BytesIO` at `scripts/update_market_data.py:1440`.
- PASS (static): next session derives from one verified receipt `expected_date` at `scripts/update_market_data.py:1351`.
- PARTIAL: rollback fsyncs replacement and parent directory at `scripts/update_market_data.py:1383`; post-commit prune remains nonfatal. Windows failure paths are not covered by the required shared suites.

## Verification

- `python -m py_compile ...`: PASS.
- `git diff --check ...`: PASS.
- Targeted Windows suite: `13 passed, 8 skipped`.
- Combined relevant Windows suite, 39 collected: `16 passed, 8 skipped, 15 failed`.
- Failing suites: `tests/test_market_release_gates.py` (`12 failed, 3 passed`) and `tests/test_vci_updater_validation_write_blocker.py` (`3 failed`).
- Root causes: strict aware timestamp exceptions escape `validate_release_gates` at `scripts/update_market_data.py:1294`; unskipped Windows tests attempt durable receipt/publication paths and receive the intended fail-closed durability error.

## Required Remediation

1. Reorder exception canonical-hash recomputation before all exception semantic checks; add a regression proving the priority.
2. Replace unlink-then-reacquire stale lock recovery with atomic owner-token recovery; add a contention regression.
3. Make the full relevant Windows suite contract-aware: preserve fail-closed behavior, skip or assert it consistently, and ensure release validation returns its documented gate result rather than leaking timestamp exceptions where applicable.
4. Restore `vci_final_safety_closure_plan.md` to the repository/session evidence before resubmission.

## Verdict

[NEEDS_FIX]
